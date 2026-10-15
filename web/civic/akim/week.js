/*
 * Birge · «Картина недели» (R08, раунд 15): отчёт для совещания — экран и печать A4, ҚАЗ / РУС.
 *
 * Страница — /civic/akim/week.html (data-autostart). Данные — GET {apiBase}/akim/week?date=YYYY-MM-DD&district=<id>
 * (ui/civic_akim/weekly.py, только сотрудник; 401 → «Войдите как сотрудник»). Все числа считает сервер: неделя —
 * 7 календарных дней, последний — date; по дням столбики = «поступило за неделю»; «в работе» и «просрочено» — на
 * конец недели (как «Картина дня» этого дня); темы, районы, места — тепловая карта R07 за 7 дней. Блоки служб (R17),
 * жителей (R16) и встреч (R13) — только у недели, которая заканчивается сегодня (у соседей нет истории «на дату»).
 * Лист 1 — главное (числа, по дням, темы, районы, места); лист 2 — службы, кризис, жители, встречи, решения, объекты,
 * прогноз (прототип). Пустой блок не печатается. Адрес: ?date=…&district=…&lang=kk (F5 и ссылка показывают то же).
 * Тексты — словарь R11; ключей akim.week.* ещё нет — запасной текст WEEK_KEYS (список для R11 — INTEGRATION.txt).
 */
(function (root) {
  "use strict";

  var doc = root.document;
  var script = doc.currentScript;
  var scriptBase = ((script && script.src) || "").replace(/[^/]*$/, "");
  var ICONS = scriptBase + "../ui-kit/icons.svg";
  var ASTANA_OFFSET_MS = 5 * 3600 * 1000;
  var DISTRICT_IDS = ["almaty", "baikonur", "esil", "nura", "saraishyk", "saryarka"];

  var WEEK_KEYS = {
    ru: {
      "akim.week.title": "Картина недели",
      "akim.week.scope_city": "Весь город",
      "akim.week.scope_district": "Район {name}",
      "akim.week.as_of": "По состоянию на {date}, {time}",
      "akim.week.closed": "Неделя закрыта",
      "akim.week.date": "Неделя по",
      "akim.week.district": "Район",
      "akim.week.print": "Распечатать",
      "akim.week.back": "Картина дня",
      "akim.week.summary": "Коротко о неделе",
      "akim.week.kpi.new": "Поступило",
      "akim.week.kpi.fixed": "Служба сообщила об исправлении",
      "akim.week.kpi.verified": "жители подтвердили: {n}",
      "akim.week.kpi.reopened": "вернули жители: {n}",
      "akim.week.kpi.in_progress": "В работе сейчас",
      "akim.week.kpi.overdue": "Просрочено сейчас",
      "akim.week.vs": "к прошлой неделе",
      "akim.week.days": "Новые обращения по дням",
      "akim.week.days_legend_now": "эта неделя",
      "akim.week.days_legend_prev": "неделей раньше",
      "akim.week.days_partial": "сегодня — до {time}",
      "akim.week.topics": "Темы недели",
      "akim.week.districts": "Районы",
      "akim.week.people": "человек",
      "akim.week.hot": "Горячие места",
      "akim.week.agencies": "Ведомства вместе",
      "akim.week.agencies.joint": "совместных обращений за неделю",
      "akim.week.agencies.handoffs": "передач между службами",
      "akim.week.agencies.lagging": "Отстают: {list}",
      "akim.week.agencies.service": "Служба",
      "akim.week.agencies.open": "Открыто",
      "akim.week.agencies.no_answer": "Нет ответа в срок",
      "akim.week.agencies.median": "Ответ, дн.",
      "akim.week.agencies.verified": "Проверено жителями",
      "akim.week.agencies.period": "Табло служб за {n} дней",
      "akim.week.crisis": "Кризисный штаб",
      "akim.week.crisis.active": "Идёт: {title}",
      "akim.week.crisis.closed": "Закрыт за неделю: {title}",
      "akim.week.crisis.tasks": "Задачи служб: выполнено {done} из {total}",
      "akim.week.crisis.update": "Жителям: «{text}»",
      "akim.week.crisis.result": "Итог: {text}",
      "akim.week.together": "Жители вместе",
      "akim.week.together.done": "дел сделали вместе",
      "akim.week.together.people": "соседей участвовали",
      "akim.week.together.upcoming": "дел впереди",
      "akim.week.together.verified": "исправлений подтвердили жители",
      "akim.week.together.yard": "Двор недели: {name} — {deed}",
      "akim.week.meetings": "Встречи с жителями",
      "akim.week.meetings.counts": "Поручения: выполнено {done} из {total}, в работе {work}, просрочено {late}",
      "akim.week.meetings.due": "срок {date}",
      "akim.week.meetings.late": "просрочено",
      "akim.week.meetings.next": "Следующая встреча: {place}, {date} · придут {n}",
      "akim.week.decisions": "Нужно решение акима",
      "akim.week.objects": "Объекты с отставанием",
      "akim.week.objects.late": "отстаёт на {n} дн.",
      "akim.week.forecast": "Прогноз на неделю",
      "akim.week.forecast_month": "Прогноз на месяц",
      "akim.week.forecast.note": "Прототип: модель обучена на синтетической истории, не реальная оценка риска.",
      "akim.week.proto": "Прототип",
      "akim.week.chosen": "выбран акимом",
      "akim.week.past_note": "Блоки служб, жителей и встреч есть только у текущей недели.",
      "akim.week.footer": "Birge · числа считает код по данным платформы; тексты без языковой модели.",
      "akim.week.demo": "Данные — пример: обращения придуманы, улицы и дворы — OpenStreetMap.",
      "akim.week.login": "«Картина недели» — для сотрудников акимата. Войдите на главной: аватар → «Для сотрудников».",
      "akim.week.error": "Отчёт не загрузился. Проверьте связь и повторите.",
      "akim.week.loading": "Собираем картину недели…",
      "akim.week.page": "Лист {n}",
      "akim.week.months": ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"],
      "akim.week.weekdays": ["пн", "вт", "ср", "чт", "пт", "сб", "вс"],
    },
    kk: {
      "akim.week.title": "Апта қорытындысы",
      "akim.week.scope_city": "Бүкіл қала",
      "akim.week.scope_district": "{name} ауданы",
      "akim.week.as_of": "{date}, {time} жағдайы бойынша",
      "akim.week.closed": "Апта жабылды",
      "akim.week.date": "Апта соңы",
      "akim.week.district": "Аудан",
      "akim.week.print": "Басып шығару",
      "akim.week.back": "Күн қорытындысы",
      "akim.week.summary": "Апта туралы қысқаша",
      "akim.week.kpi.new": "Түскені",
      "akim.week.kpi.fixed": "Қызмет түзетілгенін хабарлады",
      "akim.week.kpi.verified": "тұрғындар растады: {n}",
      "akim.week.kpi.reopened": "тұрғындар қайтарды: {n}",
      "akim.week.kpi.in_progress": "Қазір орындалуда",
      "akim.week.kpi.overdue": "Қазір мерзімі өткен",
      "akim.week.vs": "өткен аптамен салыстырғанда",
      "akim.week.days": "Күндер бойынша жаңа өтініштер",
      "akim.week.days_legend_now": "осы апта",
      "akim.week.days_legend_prev": "алдыңғы апта",
      "akim.week.days_partial": "бүгін — {time} дейін",
      "akim.week.topics": "Апта тақырыптары",
      "akim.week.districts": "Аудандар",
      "akim.week.people": "адам",
      "akim.week.hot": "Шағымы көп орындар",
      "akim.week.agencies": "Ведомстволар бірге",
      "akim.week.agencies.joint": "аптадағы бірлескен өтініш",
      "akim.week.agencies.handoffs": "қызметтер арасындағы берілім",
      "akim.week.agencies.lagging": "Артта қалып жатыр: {list}",
      "akim.week.agencies.service": "Қызмет",
      "akim.week.agencies.open": "Ашық",
      "akim.week.agencies.no_answer": "Мерзімінде жауап жоқ",
      "akim.week.agencies.median": "Жауап, күн",
      "akim.week.agencies.verified": "Тұрғындар тексерді",
      "akim.week.agencies.period": "Қызметтер тақтасы, {n} күн",
      "akim.week.crisis": "Жедел штаб",
      "akim.week.crisis.active": "Жүріп жатыр: {title}",
      "akim.week.crisis.closed": "Аптада жабылды: {title}",
      "akim.week.crisis.tasks": "Қызмет тапсырмалары: {total} ішінен {done} орындалды",
      "akim.week.crisis.update": "Тұрғындарға: «{text}»",
      "akim.week.crisis.result": "Қорытынды: {text}",
      "akim.week.together": "Тұрғындар бірге",
      "akim.week.together.done": "бірге атқарылған іс",
      "akim.week.together.people": "көрші қатысты",
      "akim.week.together.upcoming": "алдағы іс",
      "akim.week.together.verified": "түзетуді тұрғындар растады",
      "akim.week.together.yard": "Апта ауласы: {name} — {deed}",
      "akim.week.meetings": "Тұрғындармен кездесулер",
      "akim.week.meetings.counts": "Тапсырмалар: {total} ішінен {done} орындалды, {work} жұмыста, {late} мерзімі өтті",
      "akim.week.meetings.due": "мерзімі {date}",
      "akim.week.meetings.late": "мерзімі өтті",
      "akim.week.meetings.next": "Келесі кездесу: {place}, {date} · {n} адам келеді",
      "akim.week.decisions": "Әкімнің шешімі керек",
      "akim.week.objects": "Кестеден қалып жатқан нысандар",
      "akim.week.objects.late": "{n} күнге кешігуде",
      "akim.week.forecast": "Апталық болжам",
      "akim.week.forecast_month": "Айлық болжам",
      "akim.week.forecast.note": "Прототип: модель синтетикалық тарихи деректерде оқытылған, нақты тәуекел бағасы емес.",
      "akim.week.proto": "Прототип",
      "akim.week.chosen": "әкім таңдады",
      "akim.week.past_note": "Қызметтер, тұрғындар және кездесулер блоктары тек ағымдағы аптада бар.",
      "akim.week.footer": "Birge · сандарды платформа деректері бойынша код есептейді; мәтін тілдік модельсіз.",
      "akim.week.demo": "Деректер — үлгі: өтініштер ойдан құрастырылған, көшелер мен аулалар — OpenStreetMap.",
      "akim.week.login": "«Апта қорытындысы» — әкімдік қызметкерлеріне арналған. Басты бетте кіріңіз: аватар → «Қызметкерлерге».",
      "akim.week.error": "Есеп жүктелмеді. Байланысты тексеріп, қайталаңыз.",
      "akim.week.loading": "Апта қорытындысы дайындалып жатыр…",
      "akim.week.page": "{n}-парақ",
      "akim.week.months": ["қаңтар", "ақпан", "наурыз", "сәуір", "мамыр", "маусым", "шілде", "тамыз", "қыркүйек", "қазан", "қараша", "желтоқсан"],
      "akim.week.weekdays": ["дс", "сс", "ср", "бс", "жм", "сб", "жс"],
    },
  };

  function I() {
    return root.BirgeI18n;
  }
  function lang() {
    return I() ? I().getLang() : "ru";
  }
  function num(n) {
    return I() ? I().formatNumber(n) : String(n);
  }
  function interpolate(text, params) {
    return String(text).replace(/\{(\w+)\}/g, function (whole, name) {
      if (!params || params[name] == null) return whole;
      return typeof params[name] === "number" ? num(params[name]) : String(params[name]);
    });
  }
  function own(key) {
    var l = lang() === "kk" ? "kk" : "ru";
    var v = WEEK_KEYS[l][key];
    return v == null ? WEEK_KEYS.ru[key] : v;
  }
  function tr(key, params) {
    var i18n = I();
    if (i18n && (i18n.has(key) || i18n.has(key, "ru"))) return i18n.t(key, params);
    var v = own(key);
    if (v != null && !Array.isArray(v)) return interpolate(v, params);
    return i18n ? i18n.t(key, params) : interpolate(key, params);
  }
  function list(key) {
    var v = own(key);
    return Array.isArray(v) ? v : [];
  }
  function h(tag, attrs, children) {
    var el = doc.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        var v = attrs[k];
        if (v == null || v === false) return;
        if (k === "text") el.textContent = v;
        else if (k === "class") el.className = v;
        else if (k.slice(0, 2) === "on") el.addEventListener(k.slice(2), v);
        else el.setAttribute(k, v === true ? "" : v);
      });
    }
    (children || []).forEach(function (c) {
      if (c == null || c === false) return;
      el.appendChild(typeof c === "string" ? doc.createTextNode(c) : c);
    });
    return el;
  }
  function svgEl(tag, attrs) {
    var el = doc.createElementNS("http://www.w3.org/2000/svg", tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (attrs[k] != null) el.setAttribute(k, attrs[k]);
    });
    return el;
  }
  function icon(name) {
    var svg = svgEl("svg", { class: "ic wk-ic", "aria-hidden": "true", focusable: "false" });
    svg.appendChild(svgEl("use", { href: ICONS + "#i-" + name }));
    return svg;
  }
  function label(obj, base) {
    if (!obj) return "";
    return obj[base + "_" + lang()] || obj[base + "_ru"] || "";
  }
  function districtName(id) {
    return id ? tr("district." + id) : "";
  }
  function catName(id) {
    return id && I() ? I().cat(id) : id || "";
  }
  function serviceName(svc) {
    if (!svc) return "";
    if (svc.name_edited) return svc[lang()] || svc.ru;
    return I() && I().has("service." + svc.id) ? tr("service." + svc.id) : svc[lang()] || svc.ru;
  }
  function todayAstana() {
    return new Date(Date.now() + ASTANA_OFFSET_MS).toISOString().slice(0, 10);
  }
  function fullDate(iso, withYear) {
    var p = String(iso).slice(0, 10).split("-");
    var months = list("akim.week.months");
    var m = months[+p[1] - 1] || p[1];
    return +p[2] + " " + m + (withYear ? " " + p[0] : "");
  }
  // «9–15 октября 2026», «28 сентября – 4 октября 2026».
  function periodTitle(per) {
    var a = per.from.split("-"), b = per.to.split("-");
    if (a[1] === b[1]) return +a[2] + "–" + fullDate(per.to, true);
    return fullDate(per.from, a[0] !== b[0]) + " – " + fullDate(per.to, true);
  }
  function deltaText(ch) {
    if (!ch || !ch.trend || ch.trend === "flat") return tr("akim.delta.same");
    if (ch.mode === "new") return tr("akim.delta.new");
    if (ch.mode === "ratio") return tr("akim.delta.ratio", { n: ch.ratio });
    var v = ch.mode === "pct" ? I().formatPercent(ch.pct) : num(ch.abs);
    return tr(ch.trend === "up" ? "akim.delta.more" : "akim.delta.less", { v: v });
  }

  function mount(rootEl, options) {
    options = options || {};
    var params = new URLSearchParams(root.location.search);
    var state = {
      date: /^\d{4}-\d{2}-\d{2}$/.test(params.get("date") || "") && params.get("date") <= todayAstana() ? params.get("date") : null,
      district: DISTRICT_IDS.indexOf(params.get("district")) >= 0 ? params.get("district") : null,
      status: "loading", data: null, request: 0,
    };
    var apiBase = options.apiBase || rootEl.getAttribute("data-api") || "/api/civic/v2";
    rootEl.classList.add("wk");
    rootEl.textContent = "";
    var bar = h("div", { class: "wk-bar" });
    var pages = h("div", { class: "wk-pages", "aria-live": "polite" });
    rootEl.appendChild(bar);
    rootEl.appendChild(pages);

    function syncUrl() {
      var q = new URLSearchParams(root.location.search);
      if (state.date && state.date !== todayAstana()) q.set("date", state.date);
      else q.delete("date");
      if (state.district) q.set("district", state.district);
      else q.delete("district");
      var s = q.toString();
      root.history.replaceState(root.history.state, "", root.location.pathname + (s ? "?" + s : ""));
    }
    function load() {
      var id = ++state.request;
      state.status = "loading";
      render();
      var q = new URLSearchParams();
      if (state.date) q.set("date", state.date);
      if (state.district) q.set("district", state.district);
      fetch(apiBase + "/akim/week" + (q.toString() ? "?" + q : ""), { headers: { Accept: "application/json" }, credentials: "same-origin", cache: "no-store" })
        .then(function (r) {
          return r.json().catch(function () { return null; }).then(function (b) { return { ok: r.ok, status: r.status, body: b }; });
        })
        .then(function (res) {
          if (id !== state.request) return;
          if (res.ok && res.body && res.body.totals) {
            state.status = "ok";
            state.data = res.body;
          } else state.status = res.status === 401 || res.status === 403 ? "login" : "error";
        })
        .catch(function () {
          if (id === state.request) state.status = "error";
        })
        .then(function () {
          if (id === state.request) render();
        });
    }

    // ── панель (только экран) ──
    function renderBar() {
      bar.textContent = "";
      var date = h("input", { type: "date", class: "wk-input", value: state.date || todayAstana(), max: todayAstana(), "aria-label": tr("akim.week.date"),
        onchange: function (e) {
          var v = e.target.value;
          state.date = v && v < todayAstana() ? v : null;
          syncUrl();
          load();
        } });
      var sel = h("select", { class: "wk-input", "aria-label": tr("akim.week.district"),
        onchange: function (e) {
          state.district = DISTRICT_IDS.indexOf(e.target.value) >= 0 ? e.target.value : null;
          syncUrl();
          load();
        } }, [h("option", { value: "", text: tr("akim.district.all_city") })].concat(DISTRICT_IDS.map(function (id) {
          return h("option", { value: id, selected: state.district === id ? true : null, text: districtName(id) });
        })));
      var seg = h("div", { class: "bk-seg wk-lang", role: "group", "aria-label": tr("common.lang.label") });
      ["kk", "ru"].forEach(function (l) {
        seg.appendChild(h("button", { type: "button", lang: l, "aria-pressed": String(lang() === l), text: tr("common.lang." + l),
          onclick: function () { if (I()) I().setLang(l); } }));
      });
      var back = state.district ? "?district=" + state.district : "";
      bar.appendChild(h("a", { class: "wk-back", href: "/civic/akim/" + back }, [icon("back"), tr("akim.week.back")]));
      bar.appendChild(h("label", { class: "wk-field" }, [h("span", { text: tr("akim.week.date") }), date]));
      bar.appendChild(h("label", { class: "wk-field" }, [h("span", { text: tr("akim.week.district") }), sel]));
      bar.appendChild(seg);
      bar.appendChild(h("button", { type: "button", class: "bk-btn bk-btn--primary wk-print", disabled: state.status !== "ok" ? true : null,
        onclick: function () { root.print(); } }, [icon("print"), tr("akim.week.print")]));
    }

    // ── лист: шапка ──
    function sheet(n, children) {
      return h("article", { class: "wk-sheet", "aria-label": tr("akim.week.page", { n: n }) }, children.concat([
        h("footer", { class: "wk-foot" }, [
          h("span", { text: tr("akim.week.footer") }),
          state.data.demo && state.data.demo.any ? h("span", { class: "wk-foot__demo", text: tr("akim.week.demo") }) : null,
          h("span", { class: "wk-foot__page", text: tr("akim.week.page", { n: n }) }),
        ]),
      ]));
    }
    function head(d) {
      var scope = d.district ? tr("akim.week.scope_district", { name: districtName(d.district.id) }) : tr("akim.week.scope_city");
      var when = d.is_today ? tr("akim.week.as_of", { date: fullDate(d.as_of.slice(0, 10)), time: I().formatTime(d.as_of) }) : tr("akim.week.closed");
      return h("header", { class: "wk-head" }, [
        h("div", { class: "wk-head__brand" }, [h("span", { class: "wk-mark", "aria-hidden": "true", text: "B" }), "Birge"]),
        h("h1", { class: "wk-title" }, [tr("akim.week.title"), h("span", { class: "wk-title__period", text: periodTitle(d.period) })]),
        h("p", { class: "wk-meta" }, [scope + " · " + when, d.demo && d.demo.any ? h("span", { class: "bk-tag bk-tag--demo wk-demo", text: tr("common.demo") }) : null]),
      ]);
    }
    function section(cls, titleText, children, extra) {
      var kids = (children || []).filter(Boolean);
      if (!kids.length) return null;
      return h("section", { class: "wk-sec " + cls }, [h("h2", { class: "wk-h2" }, [titleText, extra || null])].concat(kids));
    }

    // ── лист 1 ──
    function kpis(d) {
      var t = d.totals;
      function tile(kind, labelKey, ch, extra, goodWhenUp) {
        var good = ch && ch.trend && ch.trend !== "flat" && goodWhenUp != null ? (ch.trend === "up") === goodWhenUp : null;
        return h("div", { class: "wk-kpi", "data-kind": kind }, [
          h("p", { class: "wk-kpi__value", text: ch && ch.value != null ? num(ch.value) : "—" }),
          h("p", { class: "wk-kpi__label", text: tr(labelKey) }),
          h("p", { class: "wk-kpi__delta", "data-trend": ch ? ch.trend : "flat", "data-good": good == null ? null : String(good) }, [deltaText(ch) + " " + tr("akim.week.vs")]),
          extra ? h("p", { class: "wk-kpi__extra", text: extra }) : null,
        ]);
      }
      var f = t.fixed || {};
      var fixedExtra = t.verification_available ? [tr("akim.week.kpi.verified", { n: f.verified || 0 }),
        f.reopened_by_residents ? tr("akim.week.kpi.reopened", { n: f.reopened_by_residents }) : null].filter(Boolean).join(" · ") : null;
      return h("div", { class: "wk-kpis" }, [
        tile("new", "akim.week.kpi.new", t.new, null, false),
        tile("fixed", "akim.week.kpi.fixed", f, fixedExtra, true),
        tile("in_progress", "akim.week.kpi.in_progress", t.in_progress, t.in_progress && t.in_progress.waiting ? tr("akim.kpi.waiting", { n: t.in_progress.waiting }) : null, null),
        tile("overdue", "akim.week.kpi.overdue", t.overdue, null, false),
      ]);
    }
    function dayChart(d) {
      var days = d.days || [];
      if (!days.length) return null;
      var W = 640, H = 150, padL = 8, padB = 30, padT = 18;
      var max = days.reduce(function (m, x) { return Math.max(m, x.new, x.prev); }, 0) || 1;
      var slot = (W - padL * 2) / days.length;
      var bw = Math.min(34, slot * 0.36);
      var svg = svgEl("svg", { class: "wk-chart", viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": tr("akim.week.days") });
      var wd = list("akim.week.weekdays");
      days.forEach(function (x, i) {
        var cx = padL + slot * i + slot / 2;
        var hp = (x.prev / max) * (H - padB - padT), hn = (x.new / max) * (H - padB - padT);
        svg.appendChild(svgEl("rect", { class: "wk-chart__prev", x: (cx - bw - 2).toFixed(1), y: (H - padB - hp).toFixed(1), width: bw.toFixed(1), height: Math.max(0, hp).toFixed(1), rx: "3" }));
        svg.appendChild(svgEl("rect", { class: "wk-chart__now" + (x.partial ? " is-partial" : ""), x: (cx + 2).toFixed(1), y: (H - padB - hn).toFixed(1), width: bw.toFixed(1), height: Math.max(0, hn).toFixed(1), rx: "3" }));
        var v = svgEl("text", { class: "wk-chart__num", x: (cx + 2 + bw / 2).toFixed(1), y: (H - padB - hn - 5).toFixed(1), "text-anchor": "middle" });
        v.appendChild(doc.createTextNode(num(x.new)));
        svg.appendChild(v);
        var lbl = svgEl("text", { class: "wk-chart__day", x: cx.toFixed(1), y: (H - padB + 15).toFixed(1), "text-anchor": "middle" });
        lbl.appendChild(doc.createTextNode((wd[(x.weekday || 1) - 1] || "") + " " + String(x.date).slice(8, 10).replace(/^0/, "")));
        svg.appendChild(lbl);
      });
      var partial = days.filter(function (x) { return x.partial; })[0];
      return h("figure", { class: "wk-chart-box" }, [
        svg,
        h("figcaption", { class: "wk-legend" }, [
          h("span", { class: "wk-legend__now", text: tr("akim.week.days_legend_now") }),
          h("span", { class: "wk-legend__prev", text: tr("akim.week.days_legend_prev") }),
          partial ? h("span", { text: tr("akim.week.days_partial", { time: I().formatTime(d.as_of) }) }) : null,
        ]),
      ]);
    }
    function rowsTable(rows, cls) {
      return h("ol", { class: "wk-rows " + (cls || "") }, rows.map(function (r) {
        return h("li", { class: "wk-row" }, [
          h("span", { class: "wk-row__name", text: r.name }),
          h("span", { class: "wk-row__value", text: num(r.value) }),
          h("span", { class: "wk-row__delta", "data-trend": r.ch ? r.ch.trend : "flat", text: r.ch ? deltaText(r.ch) : "" }),
        ]);
      }));
    }
    function page1(d) {
      var topics = ((d.topics && d.topics.items) || []).map(function (t) {
        return { name: label(t, "") || t[lang()] || t.ru, value: t.value, ch: t };
      });
      var dist = ((d.districts && d.districts.items) || []).map(function (r) {
        return { name: r[lang()] || r.ru, value: r.value, ch: r };
      });
      var hot = ((d.hot && d.hot.items) || []).map(function (it) {
        return h("li", { class: "wk-hot" }, [
          h("span", { class: "wk-hot__rank", "data-level": String(it.level || 1), text: String(it.rank) }),
          h("span", { class: "wk-hot__name" }, [label(it.target, "label") || catName(it.category), h("span", { class: "wk-sub", text: [catName(it.category), districtName(it.district)].filter(Boolean).join(" · ") })]),
          h("span", { class: "wk-hot__count", text: num(it.count) + " " + tr("akim.week.people") }),
        ]);
      });
      var text = (d.text && (d.text[lang()] || d.text.ru)) || [];
      return sheet(1, [
        head(d),
        h("section", { class: "wk-sec wk-summary" }, [h("h2", { class: "wk-h2 wk-sr", text: tr("akim.week.summary") }), h("p", { class: "wk-summary__text", text: text.join(" ") })]),
        d.complaints_available === false ? null : kpis(d),
        section("wk-days", tr("akim.week.days"), [dayChart(d)]),
        h("div", { class: "wk-cols" }, [
          section("wk-topics", tr("akim.week.topics"), [topics.length ? rowsTable(topics) : null]),
          section("wk-districts", tr("akim.week.districts"), [dist.length ? rowsTable(dist) : null]),
        ]),
        section("wk-hotbox", tr("akim.week.hot"), [hot.length ? h("ol", { class: "wk-hots" }, hot) : null]),
      ].filter(Boolean));
    }

    // ── лист 2 ──
    function agencies(d) {
      var g = d.agencies;
      if (!g || !g.available) return null;
      var rows = g.board || [];
      var table = rows.length ? h("table", { class: "wk-table" }, [
        h("thead", null, [h("tr", null, [
          h("th", { scope: "col", text: tr("akim.week.agencies.service") }),
          h("th", { scope: "col", class: "wk-num", text: tr("akim.week.agencies.open") }),
          h("th", { scope: "col", class: "wk-num", text: tr("akim.week.agencies.no_answer") }),
          h("th", { scope: "col", class: "wk-num", text: tr("akim.week.agencies.median") }),
          h("th", { scope: "col", class: "wk-num", text: tr("akim.week.agencies.verified") }),
        ])]),
        h("tbody", null, rows.map(function (r) {
          return h("tr", null, [
            h("th", { scope: "row", text: serviceName(r.service) }),
            h("td", { class: "wk-num", text: r.open == null ? "—" : num(r.open) }),
            h("td", { class: "wk-num" + (r.overdue ? " is-bad" : ""), text: r.overdue == null ? "—" : num(r.overdue) }),
            h("td", { class: "wk-num", text: r.median_answer_days == null ? "—" : num(Math.round(r.median_answer_days * 10) / 10) }),
            h("td", { class: "wk-num", text: r.verified_share == null ? "—" : I().formatPercent(r.verified_share, { fraction: true }) }),
          ]);
        })),
      ]) : null;
      var lag = (g.lagging || []).map(function (x) { return serviceName(x.service); });
      return section("wk-agencies", tr("akim.week.agencies"), [
        h("div", { class: "wk-stats" }, [
          g.joint != null ? h("p", { class: "wk-stat" }, [h("strong", { text: num(g.joint) }), " " + tr("akim.week.agencies.joint")]) : null,
          g.handoffs_week != null ? h("p", { class: "wk-stat" }, [h("strong", { text: num(g.handoffs_week) }), " " + tr("akim.week.agencies.handoffs")]) : null,
        ]),
        lag.length ? h("p", { class: "wk-line", text: tr("akim.week.agencies.lagging", { list: lag.join(", ") }) }) : null,
        table,
        table && g.board_days ? h("p", { class: "wk-note", text: tr("akim.week.agencies.period", { n: g.board_days }) }) : null,
      ], g.demo ? h("span", { class: "bk-tag bk-tag--demo wk-tag", text: tr("common.demo") }) : null);
    }
    function crisis(d) {
      var c = d.crisis;
      if (!c || !c.available || (!c.active && !(c.closed_week || []).length)) return null;
      var items = [];
      if (c.active) {
        var a = c.active;
        items.push(h("div", { class: "wk-crisis" }, [
          h("p", { class: "wk-line wk-strong", text: tr("akim.week.crisis.active", { title: label(a, "title") }) }),
          h("p", { class: "wk-line", text: tr("akim.week.crisis.tasks", { done: a.tasks_done, total: a.tasks_total }) + " · " +
            (a.services || []).map(function (s) { return serviceName(s.service) + " " + num(s.done) + "/" + num(s.total); }).join(", ") }),
          a.last_update ? h("p", { class: "wk-line", text: tr("akim.week.crisis.update", { text: label(a.last_update, "text") }) }) : null,
        ]));
      }
      (c.closed_week || []).forEach(function (x) {
        items.push(h("div", { class: "wk-crisis" }, [
          h("p", { class: "wk-line wk-strong", text: tr("akim.week.crisis.closed", { title: label(x, "title") }) }),
          x.result ? h("p", { class: "wk-line", text: tr("akim.week.crisis.result", { text: label(x.result, "text") }) }) : null,
        ]));
      });
      return section("wk-crisisbox", tr("akim.week.crisis"), items, c.demo ? h("span", { class: "bk-tag bk-tag--demo wk-tag", text: tr("common.demo") }) : null);
    }
    function together(d) {
      var t = d.together;
      if (!t || !t.available || !(t.done_week || t.upcoming || t.yard_of_week)) return null;
      var star = t.yard_of_week;
      return section("wk-together", tr("akim.week.together"), [
        h("div", { class: "wk-stats" }, [
          h("p", { class: "wk-stat" }, [h("strong", { text: num(t.done_week || 0) }), " " + tr("akim.week.together.done")]),
          h("p", { class: "wk-stat" }, [h("strong", { text: num(t.people_done || 0) }), " " + tr("akim.week.together.people")]),
          h("p", { class: "wk-stat" }, [h("strong", { text: num(t.upcoming || 0) }), " " + tr("akim.week.together.upcoming")]),
          t.verified && t.verified.available ? h("p", { class: "wk-stat" }, [h("strong", { text: num(t.verified.value || 0) }), " " + tr("akim.week.together.verified")]) : null,
        ]),
        star ? h("p", { class: "wk-line", text: tr("akim.week.together.yard", { name: star.target ? label(star.target, "label") : "", deed: label(star, "title") }) }) : null,
      ], t.demo ? h("span", { class: "bk-tag bk-tag--demo wk-tag", text: tr("common.demo") }) : null);
    }
    function meetings(d) {
      var m = d.meetings;
      if (!m || !m.available || !((m.orders && m.orders.total) || m.next)) return null;
      var o = m.orders || {};
      var rows = (m.items || []).map(function (it) {
        return h("li", { class: "wk-order" + (it.overdue ? " is-late" : "") }, [
          h("span", { class: "wk-order__text" }, [label(it, "text"), h("span", { class: "wk-sub", text: [serviceName(it.service), it.meeting ? districtName(it.meeting.district) : null].filter(Boolean).join(" · ") })]),
          h("span", { class: "wk-order__due", text: it.overdue ? tr("akim.week.meetings.late") : it.due ? tr("akim.week.meetings.due", { date: fullDate(it.due) }) : "" }),
        ]);
      });
      var nx = m.next;
      return section("wk-meetings", tr("akim.week.meetings"), [
        h("p", { class: "wk-line", text: tr("akim.week.meetings.counts", { done: o.done || 0, total: o.total || 0, work: (o.in_progress || 0) + (o.todo || 0), late: o.overdue || 0 }) }),
        rows.length ? h("ol", { class: "wk-orders" }, rows) : null,
        nx ? h("p", { class: "wk-line", text: tr("akim.week.meetings.next", { place: districtName(nx.district), date: I().formatDateTime(nx.at), n: nx.registered || 0 }) }) : null,
      ], m.demo ? h("span", { class: "bk-tag bk-tag--demo wk-tag", text: tr("common.demo") }) : null);
    }
    function decisions(d) {
      var items = (d.decisions && d.decisions.items) || [];
      if (!items.length) return null;
      return section("wk-decisions", tr("akim.week.decisions"), [h("ol", { class: "wk-decs" }, items.map(function (it) {
        return h("li", { class: "wk-dec" }, [
          h("p", { class: "wk-strong", text: label(it, "problem") }),
          h("ol", { class: "wk-dec__opts" }, (it.options || []).map(function (o, i) {
            var chosen = it.chosen && it.chosen.option === i + 1;
            return h("li", { class: chosen ? "is-chosen" : null, text: tr("akim.decision.option", { n: i + 1, text: o[lang()] || o.ru }) + (chosen ? " — " + tr("akim.week.chosen") : "") });
          })),
        ]);
      }))], d.decisions.demo ? h("span", { class: "bk-tag bk-tag--demo wk-tag", text: tr("common.demo") }) : null);
    }
    function objects(d) {
      var o = d.objects;
      if (!o || !o.available || !(o.late || []).length) return null;
      return section("wk-objects", tr("akim.week.objects"), [h("ol", { class: "wk-rows" }, o.late.map(function (x) {
        return h("li", { class: "wk-row" }, [
          h("span", { class: "wk-row__name", text: label(x, "title") }),
          h("span", { class: "wk-row__value", text: districtName(x.district) }),
          h("span", { class: "wk-row__delta", "data-trend": "up", text: tr("akim.week.objects.late", { n: x.delay_days }) }),
        ]);
      }))]);
    }
    function forecast(d) {
      var f = d.forecast;
      if (!f || !f.available || !(f.items || []).length) return null;
      return section("wk-forecast", tr(f.period === "month" ? "akim.week.forecast_month" : "akim.week.forecast"), [
        h("ol", { class: "wk-rows" }, f.items.slice(0, 3).map(function (it) {
          return h("li", { class: "wk-row wk-row--fc" }, [
            h("span", { class: "wk-level", "data-level": it.level || "low", "aria-hidden": "true" }),
            h("span", { class: "wk-row__name" }, [it.target ? label(it.target, "label") : catName(it.category), h("span", { class: "wk-sub", text: [catName(it.category), districtName(it.district), label(it, "reason")].filter(Boolean).join(" · ") })]),
            h("span", { class: "wk-row__delta", text: it.level ? tr("forecast.level." + it.level) : "" }),
          ]);
        })),
        h("p", { class: "wk-note", text: tr("akim.week.forecast.note") }),
      ], h("span", { class: "bk-tag wk-proto", text: tr("akim.week.proto") }));
    }
    // Лист 2: табло служб во всю ширину, ниже две колонки — слева кризис, жители, встречи; справа решения, объекты,
    // прогноз (так колонки примерно равны и на ru, и на kk).
    function page2(d) {
      var left = [crisis(d), together(d), meetings(d)].filter(Boolean);
      var right = [decisions(d), objects(d), forecast(d)].filter(Boolean);
      var top = agencies(d);
      if (!top && !left.length && !right.length) return d.is_today ? null : sheet(2, [h("p", { class: "wk-note", text: tr("akim.week.past_note") })]);
      return sheet(2, [
        d.is_today ? null : h("p", { class: "wk-note", text: tr("akim.week.past_note") }),
        top,
        left.length || right.length ? h("div", { class: "wk-twocol" }, [h("div", { class: "wk-col" }, left), h("div", { class: "wk-col" }, right)]) : null,
      ].filter(Boolean));
    }

    function render() {
      renderBar();
      pages.textContent = "";
      rootEl.setAttribute("aria-busy", state.status === "loading" ? "true" : "false");
      rootEl.setAttribute("data-state", state.status);
      if (state.status === "loading") {
        pages.appendChild(h("div", { class: "wk-sheet wk-sheet--state" }, [h("p", { class: "wk-state", text: tr("akim.week.loading") })]));
        return;
      }
      if (state.status === "login" || state.status === "error") {
        pages.appendChild(h("div", { class: "wk-sheet wk-sheet--state", role: "alert" }, [
          h("p", { class: "wk-state", text: tr(state.status === "login" ? "akim.week.login" : "akim.week.error") }),
          state.status === "error" ? h("button", { type: "button", class: "bk-btn bk-btn--ghost", onclick: load, text: tr("common.action.retry") }) : null,
        ]));
        return;
      }
      var d = state.data;
      pages.appendChild(page1(d));
      var p2 = page2(d);
      if (p2) pages.appendChild(p2);
      doc.title = tr("akim.week.title") + " · " + periodTitle(d.period) + " · Birge";
    }

    var off = null;
    (I() ? I().ready : Promise.resolve()).then(function () {
      if (I()) off = I().onChange(render);
      syncUrl();
      load();
    });
    var handle = {
      reload: load,
      get state() {
        return { status: state.status, date: state.date, district: state.district };
      },
      destroy: function () {
        if (off) off();
        state.request++;
        rootEl.textContent = "";
      },
    };
    rootEl.birgeWeek = handle;
    return handle;
  }

  root.BirgeWeek = { mount: mount, version: "week-r15", keys: WEEK_KEYS };
  var auto = script && script.getAttribute("data-autostart");
  if (auto) {
    var start = function () {
      var el = doc.getElementById(auto);
      if (el) mount(el, {});
    };
    if (doc.readyState === "loading") doc.addEventListener("DOMContentLoaded", start);
    else start();
  }
})(window);
