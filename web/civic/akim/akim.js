/*
 * Birge · «Картина дня» для акима (R08, раунд 14).
 *
 * Подключение (после ui-kit и i18n):
 *   <link rel="stylesheet" href="/civic/akim/akim.css">
 *   <script src="/civic/i18n/i18n.js"></script>
 *   <script src="/civic/akim/akim.js"></script>
 *   BirgeAkim.mount(document.getElementById("akim"), { apiBase: "/api/civic/v2" });
 *   Опции: mapHref, syncUrl, refreshMs (тихое обновление, 0 — выкл.), titleTag ("h1"; в оболочке со своим h1 — "h2"),
 *   objectHref (null — строки объектов не ссылки; "/#object={id}" — открыть объект на карте, событие "birge:open-object").
 *
 * Данные: GET {apiBase}/akim/summary?date=YYYY-MM-DD&district=<id> (ui/civic_akim, R08). Все числа
 * считает сервер; здесь только показ. Текст сводки приходит сразу на ru и kk — смена языка без запроса.
 *
 * Переход на карту: клик по горячему месту → событие "birge:open-target" {target, days} (отменяемое:
 * оболочка R01 может открыть цель у себя и вызвать preventDefault). Иначе — ссылка opts.mapHref
 * (по умолчанию "/#target={kind}:{id}&days={days}").
 *
 * Тексты: только ключи общего словаря R11 (web/civic/i18n, ветка claude/r14-R11) — свой akim.i18n.json
 * больше не нужен, все ключи akim.* перенесены R11 (UX_REVIEW, день 2).
 * Волна 2 (схема R11 IA_WAVE2 §5): «Нужно решение акима» (нет случаев — блока нет), «Пульс района»
 * (нет тревог — одна строка), вторая строка плитки «Исправлено» (akim.verify.split). Ключи, которых в словаре
 * R11 ещё нет, — в WAVE2_KEYS ниже (запасной текст до слияния; список для R11 — INTEGRATION.txt §8).
 * «Выбрать» вариант: POST {apiBase}/akim/decisions/<id> {option}, сотрудник, X-CSRF-Token как у R05/R06.
 */
(function (root) {
  "use strict";

  var DEFAULTS = {
    apiBase: "/api/civic/v2",
    mapHref: "/#target={kind}:{id}&days={days}",
    // Объект R06 → карта с его карточкой и этапами, напр. "/#object={id}". По умолчанию выключено: в оболочке Birge
    // (FINAL 0a7a346) выбор по #object= не показывает карточку с этапами — переход был бы «в никуда». R01 включит,
    // когда карточка объекта будет видна (INTEGRATION 4е).
    objectHref: null,
    syncUrl: true, // хранить дату и район в адресе: F5, печать и ссылка показывают то же
    refreshMs: 120000, // тихое обновление, пока вкладка видна (0 — выключить)
    titleTag: "h1", // в оболочке со своим h1 передайте "h2" — на странице будет один заголовок первого уровня
  };
  var STALE_ON_RETURN_MS = 60000; // вернулись на вкладку, а данным больше минуты — обновить
  var TIMEOUT_MS = 15000;
  var LATE_VISIBLE = 5;
  var ASTANA_OFFSET_MS = 5 * 3600 * 1000; // весь Казахстан — UTC+5 с 1 марта 2024
  var DISTRICT_IDS = ["almaty", "baikonur", "esil", "nura", "saraishyk", "saryarka"];

  var doc = root.document;
  var scriptBase = ((doc.currentScript && doc.currentScript.src) || "").replace(/[^/]*$/, "");
  var ICONS = scriptBase + "../ui-kit/icons.svg";
  var STAGES = ["planned", "design", "procurement", "construction", "acceptance", "operating"];

  // ───────────── перевод ─────────────

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
  // Ключи волны 2, которых ещё нет в словаре R11: показываем этот текст, пока R11 не добавит ключ к себе.
  // Как только ключ есть в словаре — берётся словарь (вычитанный kk), этот запас не используется.
  var WAVE2_KEYS = {
    ru: {
      "akim.pulse.spike_new": "{category} · {district}: раньше такого не было",
      "akim.pulse.spike_city": { one: "{category}: всплеск в {n} районе, ×{k}", few: "{category}: всплеск в {n} районах, ×{k}", many: "{category}: всплеск в {n} районах, ×{k}" },
      "akim.pulse.reason.spike": { one: "{n} сообщение за 7 дней, обычно {base} в неделю", few: "{n} сообщения за 7 дней, обычно {base} в неделю", many: "{n} сообщений за 7 дней, обычно {base} в неделю" },
      "akim.pulse.reason.spike_new": { one: "{n} сообщение за 7 дней, раньше — ни одного", few: "{n} сообщения за 7 дней, раньше — ни одного", many: "{n} сообщений за 7 дней, раньше — ни одного" },
      "akim.pulse.reason.city": "Больше всего: {list}",
      "akim.pulse.reason.new_hot": { one: "{n} человек за 7 дней, неделю назад места на карте не было", few: "{n} человека за 7 дней, неделю назад места на карте не было", many: "{n} человек за 7 дней, неделю назад места на карте не было" },
      "akim.pulse.reason.metoo": "Неделей раньше — {n}",
      "akim.pulse.more": { one: "Ещё {n} тревога", few: "Ещё {n} тревоги", many: "Ещё {n} тревог" },
      "akim.overdue.longest": "Дольше всех: {place}",
      "akim.decision.no_options": "Варианты не предложены — служба должна их подготовить",
      "akim.decision.forbidden": "Выбрать вариант может только сотрудник акимата",
      "akim.decision.save_error": "Выбор не сохранился — попробуйте ещё раз",
    },
    kk: {
      "akim.pulse.spike_new": "{category} · {district}: бұрын болмаған",
      "akim.pulse.spike_city": "{category}: {n} ауданда күрт өсу, ×{k}",
      "akim.pulse.reason.spike": "7 күнде {n} хабарлама, әдетте аптасына {base}",
      "akim.pulse.reason.spike_new": "7 күнде {n} хабарлама, бұрын — бірде-бір",
      "akim.pulse.reason.city": "Ең көбі: {list}",
      "akim.pulse.reason.new_hot": "7 күнде {n} адам, бір апта бұрын бұл орын картада болмаған",
      "akim.pulse.reason.metoo": "Алдыңғы аптада — {n}",
      "akim.pulse.more": "Тағы {n}",
      "akim.overdue.longest": "Ең ұзағы: {place}",
      "akim.decision.no_options": "Нұсқалар ұсынылмаған — оларды қызмет дайындауы керек",
      "akim.decision.forbidden": "Нұсқаны тек әкімдік қызметкері таңдай алады",
      "akim.decision.save_error": "Таңдау сақталмады — қайталап көріңіз",
    },
  };
  function wave2(key, params) {
    var l = lang() === "kk" ? "kk" : "ru";
    var v = WAVE2_KEYS[l][key];
    if (v == null) return null;
    if (typeof v === "object") {
      var n = params && params.n != null ? Number(params.n) : 0;
      var cat = I() ? I().plural(l, n) : "many";
      v = v[cat] || v.other || v.many || v.few || v.one;
    }
    return interpolate(v, params);
  }
  function tr(key, params) {
    var i18n = I();
    if (!i18n) return wave2(key, params) || interpolate(key, params);
    if (!i18n.has(key) && !i18n.has(key, "ru") && WAVE2_KEYS.ru[key] != null) return wave2(key, params);
    return i18n.t(key, params);
  }

  // ───────────── мелкие помощники ─────────────

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
  function icon(name, size) {
    var svg = doc.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "ic" + (size ? " ic--" + size : ""));
    svg.setAttribute("aria-hidden", "true");
    var use = doc.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", ICONS + "#i-" + name);
    svg.appendChild(use);
    return svg;
  }
  function todayAstana() {
    return new Date(Date.now() + ASTANA_OFFSET_MS).toISOString().slice(0, 10);
  }
  // Подпись на текущем языке: label_kk / title_kk, если есть, иначе русская.
  // kindPrefix: если казахского названия нет (сервер ставит title_kk_missing), в ҚАЗ показываем вид объекта
  // по-казахски из словаря R11 («object.kind.roadworks» → «Жол жөндеу»), а не русскую строку (R10 B-018).
  function label(obj, base, kindPrefix) {
    var l = lang();
    if (!obj) return "";
    if (l !== "ru" && obj[base + "_" + l + "_missing"] && kindPrefix && obj.kind && I() && I().has(kindPrefix + obj.kind)) {
      return tr(kindPrefix + obj.kind);
    }
    return obj[base + "_" + l] || obj[base + "_ru"] || "";
  }
  function districtName(id) {
    return id ? tr("district." + id) : tr("akim.district.all_city");
  }
  function lowerFirst(text) {
    return text ? text.charAt(0).toLocaleLowerCase(lang()) + text.slice(1) : text;
  }
  function demoTag() {
    return h("span", { class: "bk-tag bk-tag--demo", title: tr("common.tag.demo_hint"), text: tr("common.tag.demo") });
  }

  // Изменение к прошлой неделе: стрелка (CSS) + слово. Цвет никогда не один.
  // «в 6,9 раза»: у дробных по-русски форма как у 2–4. В словаре R11 у akim.delta.ratio нет формы other,
  // а i18n.js для дробных берёт many («раз») — поэтому форму выбираем по 2 и подставляем настоящее число.
  // Когда R11 добавит ru other «в {n} раза больше» (INTEGRATION.txt п. 7), обход ничего не меняет.
  function ratioText(n) {
    if (n % 1 === 0 || lang() !== "ru") return tr("akim.delta.ratio", { n: n });
    var probe = tr("akim.delta.ratio", { n: 2 });
    return probe.indexOf(num(2)) >= 0 ? probe.replace(num(2), num(n)) : tr("akim.delta.ratio", { n: n });
  }
  function deltaText(ch) {
    if (!ch || ch.trend === "flat") return tr("akim.delta.same");
    if (ch.mode === "new") return tr("akim.delta.new");
    if (ch.mode === "ratio") return ratioText(ch.ratio);
    var v = ch.mode === "pct" ? I().formatPercent(ch.pct) : num(ch.abs);
    return tr(ch.trend === "up" ? "akim.delta.more" : "akim.delta.less", { v: v });
  }
  function deltaEl(ch, goodWhenUp) {
    var good = null;
    if (ch && ch.trend !== "flat" && goodWhenUp != null) good = (ch.trend === "up") === goodWhenUp;
    return h("span", {
      class: "bk-kpi__delta",
      "data-trend": ch ? ch.trend : "flat",
      "data-good": good == null ? null : String(good),
      text: deltaText(ch),
    });
  }
  function needsVs(ch) {
    return ch && ch.trend !== "flat" && ch.mode !== "new";
  }

  // ───────────── модуль ─────────────

  function mount(rootEl, options) {
    var opts = {};
    Object.keys(DEFAULTS).forEach(function (k) {
      opts[k] = options && options[k] != null ? options[k] : DEFAULTS[k];
    });
    var params = new URLSearchParams(root.location.search);
    var state = {
      date: /^\d{4}-\d{2}-\d{2}$/.test(params.get("date") || "") ? params.get("date") : null,
      district: DISTRICT_IDS.indexOf(params.get("district")) >= 0 ? params.get("district") : null,
      status: "loading",
      data: null,
      error: null,
      request: 0,
    };
    if (state.date && state.date > todayAstana()) state.date = null;

    rootEl.classList.add("akim");
    var top = h("div", { class: "akim__top" });
    var body = h("div", { class: "akim__body", "aria-live": "polite", "aria-busy": "true" });
    rootEl.textContent = "";
    rootEl.appendChild(top);
    rootEl.appendChild(body);

    function syncUrl() {
      if (!opts.syncUrl || !root.history || !root.history.replaceState) return;
      var q = new URLSearchParams(root.location.search);
      if (state.date && state.date !== todayAstana()) q.set("date", state.date);
      else q.delete("date");
      if (state.district) q.set("district", state.district);
      else q.delete("district");
      var s = q.toString();
      root.history.replaceState(root.history.state, "", root.location.pathname + (s ? "?" + s : "") + root.location.hash);
    }

    // silent: тихое обновление поверх показанных данных — без скелетона; при ошибке старые числа остаются.
    function load(silent) {
      silent = silent === true && state.status === "ok";
      var id = ++state.request;
      if (!silent) {
        state.status = "loading";
        render();
      }
      var q = new URLSearchParams();
      if (state.date) q.set("date", state.date);
      if (state.district) q.set("district", state.district);
      var ctrl = typeof AbortController === "function" ? new AbortController() : null;
      var timer = setTimeout(function () {
        if (ctrl) ctrl.abort();
      }, TIMEOUT_MS);
      fetch(opts.apiBase + "/akim/summary" + (q.toString() ? "?" + q : ""), {
        headers: { Accept: "application/json" },
        signal: ctrl ? ctrl.signal : undefined,
      })
        .then(function (r) {
          return r
            .json()
            .catch(function () {
              return null;
            })
            .then(function (b) {
              return { ok: r.ok, status: r.status, body: b };
            });
        })
        .then(function (res) {
          if (id !== state.request) return; // пришёл ответ на старый запрос
          if (silent) {
            if (res.ok && res.body && res.body.kpi) applySilent(res.body);
            return;
          }
          if (res.ok && res.body && res.body.kpi) {
            state.status = "ok";
            state.data = res.body;
            state.loadedAt = Date.now();
          } else {
            state.status = "error";
            state.error = res.status === 400 && res.body && res.body.field === "date" ? "date" : "server";
          }
        })
        .catch(function () {
          if (id !== state.request || silent) return; // тихое обновление не сменяет числа ошибкой
          state.status = "error";
          state.error = "network";
        })
        .then(function () {
          clearTimeout(timer);
          if (id === state.request && !silent) render();
        });
    }

    // Новые данные при тихом обновлении: перерисовываем, только если что-то изменилось (иначе — лишь «Данные на …»),
    // и возвращаем фокус туда же — экран не прыгает под руками.
    function sameData(a, b) {
      function strip(d) {
        var c = {};
        Object.keys(d || {}).forEach(function (k) {
          if (["generated_at", "as_of", "compare_to", "compute_ms"].indexOf(k) < 0) c[k] = d[k];
        });
        return JSON.stringify(c);
      }
      return strip(a) === strip(b);
    }
    function focusKey() {
      var el = doc.activeElement;
      if (!el || el === doc.body || !rootEl.contains(el)) return null;
      return el.id ? "#" + el.id : el.getAttribute("data-key") ? '[data-key="' + el.getAttribute("data-key") + '"]' : null;
    }
    function applySilent(data) {
      var changed = !sameData(state.data, data);
      state.data = data;
      state.loadedAt = Date.now();
      if (!changed) {
        renderTop();
        return;
      }
      var key = focusKey();
      var y = root.scrollY;
      render();
      if (key) {
        var again = rootEl.querySelector(key);
        if (again) again.focus({ preventScroll: true });
      }
      if (root.scrollY !== y) root.scrollTo(root.scrollX, y);
    }
    function refreshIfVisible() {
      if (doc.visibilityState === "hidden" || state.status !== "ok") return;
      load(true);
    }
    function onVisible() {
      if (doc.visibilityState === "visible" && state.status === "ok" && Date.now() - (state.loadedAt || 0) > STALE_ON_RETURN_MS)
        load(true);
    }
    var refreshTimer = opts.refreshMs > 0 ? setInterval(refreshIfVisible, opts.refreshMs) : null;
    doc.addEventListener("visibilitychange", onVisible);

    function setDate(value) {
      var today = todayAstana();
      state.date = !value || value >= today ? null : value;
      syncUrl();
      load();
    }
    function setDistrict(value) {
      state.district = DISTRICT_IDS.indexOf(value) >= 0 ? value : null;
      syncUrl();
      load();
    }

    // ── шапка страницы: заголовок, дата, район, печать ──
    function renderTop() {
      var d = state.data;
      var date = state.date || todayAstana();
      var isToday = date === todayAstana();
      top.textContent = "";
      var meta = [districtName(state.district)];
      if (d && state.status === "ok") {
        meta.push(d.is_today ? tr("akim.updated", { time: I().formatTime(d.as_of) }) : tr("akim.updated_end"));
        meta.push(tr("akim.compare_to", { date: I().formatDate(d.compare_to) }));
      }
      var title = h("div", { class: "akim__titlebox" }, [
        h(/^h[1-3]$/.test(opts.titleTag) ? opts.titleTag : "h1", { class: "akim__title" }, [
          tr("akim.title"),
          h("span", { class: "akim__title-date", text: " · " + I().formatDate(date) }),
          // Метка «Пример» — одна на страницу, здесь; в карточках её нет (UX_REVIEW день 3, п. 11).
          d && state.status === "ok" && d.demo && d.demo.any ? demoTag() : null,
        ]),
        h("p", { class: "akim__meta bk-meta", text: meta.join(" · ") }),
        // Пояснение к метке «Пример» — в шапке под датой, а не отдельной строкой над числами: так первая карточка
        // «Нужно решение акима» помещается в первый экран ноутбука (R11 IA_WAVE2 §5).
        d && state.status === "ok" && d.demo && d.demo.any
          ? h("p", { class: "akim-demo", text: tr("common.tag.demo") + ": " + lowerFirst(tr("akim.demo_note")) })
          : null,
      ]);

      var dateInput = h("input", {
        type: "date",
        id: "akim-date",
        value: date,
        max: todayAstana(),
        onchange: function (e) {
          setDate(e.target.value);
        },
      });
      var districtSelect = h(
        "select",
        {
          id: "akim-district",
          onchange: function (e) {
            setDistrict(e.target.value);
          },
        },
        [h("option", { value: "", text: tr("district.all") })].concat(
          DISTRICT_IDS.map(function (id) {
            return h("option", { value: id, text: tr("district." + id), selected: state.district === id });
          })
        )
      );
      var controls = h("div", { class: "akim__controls" }, [
        h("label", { class: "akim__field", for: "akim-date" }, [h("span", { class: "akim__field-label", text: tr("akim.date") }), dateInput]),
        isToday
          ? null
          : h("button", {
              type: "button",
              class: "bk-btn akim__today",
              text: tr("akim.date.today"),
              onclick: function () {
                setDate(null);
              },
            }),
        h("label", { class: "akim__field", for: "akim-district" }, [
          h("span", { class: "akim__field-label", text: tr("heat.filter.district") }),
          districtSelect,
        ]),
        h(
          "button",
          {
            type: "button",
            class: "bk-btn akim__print",
            onclick: function () {
              printPage();
            },
          },
          [icon("print"), tr("common.action.print")]
        ),
      ]);
      top.appendChild(title);
      top.appendChild(controls);
    }

    // ── состояния ──
    function renderLoading() {
      var kpis = h("div", { class: "bk-kpis" });
      for (var i = 0; i < 4; i++) kpis.appendChild(h("div", { class: "bk-kpi akim-kpi" }, [h("div", { class: "bk-skel bk-skel--block akim-skel-kpi" })]));
      body.appendChild(kpis);
      body.appendChild(
        h("div", { class: "bk-card akim-card akim-loading", role: "status" }, [
          h("div", { class: "bk-skel bk-skel--line" }),
          h("div", { class: "bk-skel bk-skel--line" }),
          h("p", { class: "bk-meta", text: tr("akim.loading") }),
        ])
      );
    }
    function renderError() {
      var kind = state.error;
      var box = h("div", { class: "bk-card akim-card" }, [
        h("div", { class: "bk-error", role: "alert" }, [
          icon(kind === "network" ? "wifi-off" : "alert", 48),
          h("p", {
            class: "bk-error__title",
            text: kind === "network" ? tr("common.state.network_title") : kind === "date" ? tr("akim.bad_date") : tr("common.state.error_title"),
          }),
          kind === "date"
            ? null
            : h("p", { class: "bk-error__text", text: kind === "network" ? tr("common.state.network_text") : tr("common.state.error_text") }),
          h(
            "button",
            {
              type: "button",
              class: "bk-btn bk-btn--primary",
              onclick: function () {
                if (kind === "date") setDate(null);
                else load();
              },
            },
            kind === "date" ? [tr("akim.date.today")] : [icon("refresh"), tr("common.action.retry")]
          ),
        ]),
      ]);
      body.appendChild(box);
    }

    // ── четыре крупных числа ──
    function kpiCard(kind, ch, labelKey, goodWhenUp, extra) {
      return h("article", { class: "bk-kpi akim-kpi", "data-kind": kind }, [
        h("span", { class: "bk-kpi__value", text: num(ch.value) }),
        h("span", { class: "bk-kpi__label", text: tr(labelKey) }),
        deltaEl(ch, goodWhenUp),
        needsVs(ch) ? h("span", { class: "akim-kpi__vs", text: tr("akim.delta.vs_week") }) : null,
        extra ? h("span", { class: "akim-kpi__extra" }, extra) : null,
      ]);
    }
    function renderKpis(d) {
      var k = d.kpi;
      var week = k.new_week;
      return h("section", { class: "bk-kpis akim-kpis", "aria-label": tr("akim.title") }, [
        // «За 7 дней» — вторая стрелка в карточке; на телефоне скрыта (akim.css, < 480 px), там одно изменение.
        kpiCard("new", k.new_day, "akim.kpi.new", false, [
          h("span", { class: "akim-kpi__week" }, [tr("akim.kpi.week", { n: week.value }) + " · ", deltaEl(week, false)]),
        ]),
        kpiCard("in_progress", k.in_progress, "akim.kpi.in_progress", null,
          k.in_progress.waiting ? [tr("akim.kpi.waiting", { n: k.in_progress.waiting })] : null),
        kpiCard("overdue", k.overdue, "akim.kpi.overdue", false, overdueExtra(d)),
        // Волна 2 п. 1: «Служба сообщила 12 · жители проверили 8 · вернули 2». Нет проверки жителями в данных —
        // прежняя подсказка, а не «проверили 0».
        kpiCard("fixed", k.fixed_week, "akim.kpi.fixed_week", true, [
          k.verification_available
            ? tr("akim.verify.split", { a: k.fixed_week.awaiting, b: k.fixed_week.verified, c: k.fixed_week.reopened || 0 })
            : tr("akim.kpi.fixed_hint"),
        ]),
      ]);
    }
    // Волна мелочей п. 6: таймер в «Картине дня» — самое давнее просроченное место прямо в плитке.
    function overdueExtra(d) {
      var o = d.overdue && d.overdue.items && d.overdue.items[0];
      if (!o) return [tr("akim.kpi.overdue_hint")];
      return [
        tr("akim.overdue.longest", { place: placeName(o) }) + " · ",
        h("span", { class: "akim-late-days", text: timerText(o.timer) }),
      ];
    }
    function placeName(x) {
      var l = lang();
      if (x["place_" + l] || x.place_ru) return x["place_" + l] || x.place_ru;
      if (x.subtopic && x.subtopic.id) return tr("subtopic." + x.subtopic.id);
      return x.category ? I().cat(x.category) : "";
    }
    function timerText(t) {
      if (!t) return "";
      if (t.state === "overdue") return tr("deadline.overdue", { n: t.overdue_by });
      if (t.state === "today") return tr("deadline.today");
      return tr("deadline.left", { n: t.left });
    }
    function serviceName(svc) {
      if (!svc) return "";
      if (svc.name_edited) return svc[lang()] || svc.ru; // акимат переименовал службу — его название как есть
      return I() && I().has("service." + svc.id) ? tr("service." + svc.id) : svc[lang()] || svc.ru;
    }

    // ── «Нужно решение акима» (волна 2 п. 5) ──
    var csrfCache = null;
    function csrf() {
      try {
        var shell = root.CivicShell && typeof root.CivicShell.csrfToken === "function" ? root.CivicShell.csrfToken() : null;
        if (shell) return Promise.resolve(shell);
      } catch (e) {
        /* оболочки нет */
      }
      if (csrfCache) return Promise.resolve(csrfCache);
      return fetch("/api/civic/v1/session", { credentials: "same-origin", headers: { Accept: "application/json" } })
        .then(function (r) {
          return r.json();
        })
        .then(function (b) {
          var data = b && b.data && typeof b.data === "object" ? b.data : b || {};
          csrfCache = data.authenticated && typeof data.csrf_token === "string" ? data.csrf_token : null;
          return csrfCache;
        })
        .catch(function () {
          return null;
        });
    }
    function chooseOption(item, n, statusEl) {
      statusEl.textContent = "";
      return csrf()
        .then(function (token) {
          var headers = { Accept: "application/json", "Content-Type": "application/json" };
          if (token) headers["X-CSRF-Token"] = token;
          return fetch(opts.apiBase + "/akim/decisions/" + encodeURIComponent(item.id), {
            method: "POST",
            credentials: "same-origin",
            headers: headers,
            body: JSON.stringify({ option: n }),
          });
        })
        .then(function (r) {
          if (r.ok) {
            item.chosen = { option: n };
            render();
            var again = rootEl.querySelector('[data-key="decision:' + item.id + '"]');
            if (again) again.focus({ preventScroll: true });
            load(true);
            return;
          }
          statusEl.textContent = tr(r.status === 401 || r.status === 403 ? "akim.decision.forbidden" : "akim.decision.save_error");
        })
        .catch(function () {
          statusEl.textContent = tr("akim.decision.save_error");
        });
    }
    function renderDecisions(d) {
      var items = (d.decisions && d.decisions.items) || [];
      if (!items.length) return null; // нет случаев — блока нет (IA_WAVE2 §5)
      var card = h("section", { class: "bk-card akim-card akim-decisions", "aria-labelledby": "akim-decisions-title" }, [
        h("h2", { class: "bk-h2", id: "akim-decisions-title", text: tr("akim.decision.title") }),
      ]);
      var list = h("ol", { class: "akim-decisions__list" });
      items.forEach(function (it) {
        var l = lang();
        var where = [placeName(it), it.district ? tr("district." + it.district) : null].filter(Boolean).join(" · ");
        var status = h("p", { class: "akim-decision__status", role: "status" });
        var opts2 = h("ol", { class: "akim-decision__options" });
        (it.options || []).forEach(function (o, i) {
          var n = i + 1;
          var chosen = it.chosen && it.chosen.option === n;
          opts2.appendChild(
            h("li", { class: "akim-decision__option" + (chosen ? " is-chosen" : "") }, [
              h("span", { class: "akim-decision__option-text", text: tr("akim.decision.option", { n: n, text: o[l] || o.ru }) }),
              chosen
                ? h("span", { class: "bk-tag akim-decision__chosen" }, [icon("check", 18), tr("akim.decision.chosen", { n: n })])
                : h("button", {
                    type: "button",
                    class: "bk-btn akim-decision__choose",
                    "data-key": "decision:" + it.id + ":" + n,
                    "aria-label": tr("akim.decision.choose") + ": " + tr("akim.decision.option", { n: n, text: o[l] || o.ru }),
                    text: tr("akim.decision.choose"),
                    onclick: function () {
                      chooseOption(it, n, status);
                    },
                  }),
            ])
          );
        });
        // Слева — проблема и что мешает; справа — что нужно и два варианта (на телефоне всё одной колонкой).
        list.appendChild(
          h("li", { class: "akim-decision", tabindex: "-1", "data-key": "decision:" + it.id }, [
            h("div", { class: "akim-decision__info" }, [
              h("p", { class: "akim-decision__problem" }, [h("strong", { text: it["problem_" + l] || it.problem_ru })]),
              h("p", { class: "akim-decision__meta bk-meta" }, [
                where ? where + " · " : "",
                h("span", { class: "akim-late-days", text: timerText(it.timer) }),
                " · " + tr("service.assigned", { service: serviceName(it.service) }),
              ]),
              it.blocker_ru ? h("p", { class: "akim-decision__blocker", text: tr("akim.decision.blocker", { text: it["blocker_" + l] || it.blocker_ru }) }) : null,
              it.temp_measure_ru ? h("p", { class: "bk-meta", text: tr("passport.temp_measure", { text: it["temp_measure_" + l] || it.temp_measure_ru }) }) : null,
            ]),
            h("div", { class: "akim-decision__choice" }, [
              it.decision_ru ? h("p", { class: "akim-decision__needed", text: tr("akim.decision.needed", { text: it["decision_" + l] || it.decision_ru }) }) : null,
              it.options && it.options.length ? opts2 : h("p", { class: "akim-decision__blocker bk-meta", text: tr("akim.decision.no_options") }),
              status,
            ]),
          ])
        );
      });
      card.appendChild(list);
      return card;
    }

    // ── «Пульс района» (волна 2 п. 8) ──
    function fmtK(k) {
      return num(k);
    }
    function pulseRow(a) {
      var l = lang();
      var cat = a.category ? I().cat(a.category) : "";
      var dist = a.district ? tr("district." + a.district) : "";
      var place = a.target ? label(a.target, "label") || (I().has("heat.kind." + a.target.kind) ? tr("heat.kind." + a.target.kind) : "") : "";
      var title, reason;
      if (a.kind === "spike") {
        title = tr("akim.pulse.spike", { category: cat, district: dist, k: fmtK(a.k) });
        reason = tr("akim.pulse.reason.spike", { n: a.value, base: num(a.base >= 3 ? Math.round(a.base) : a.base) });
      } else if (a.kind === "spike_new") {
        title = tr("akim.pulse.spike_new", { category: cat, district: dist });
        reason = tr("akim.pulse.reason.spike_new", { n: a.value });
      } else if (a.kind === "spike_city") {
        var names = (a.districts || []).slice(0, 3).map(function (x) {
          return tr("district." + x.district) + " — " + num(x.value);
        });
        title = tr("akim.pulse.spike_city", { category: cat, n: (a.districts || []).length, k: fmtK(a.k) });
        reason = tr("akim.pulse.reason.city", { list: names.join(", ") });
      } else if (a.kind === "new_hot") {
        title = tr("akim.pulse.new_hot", { place: place });
        reason = tr("akim.pulse.reason.new_hot", { n: a.value });
      } else {
        title = tr("akim.pulse.metoo_growth", { place: place, n: a.value });
        reason = tr("akim.pulse.reason.metoo", { n: a.prev || 0 });
      }
      var link = a.target
        ? h("a", {
            class: "akim-pulse__map",
            href: mapLink(a.target, (d0() && d0().hot && d0().hot.days) || 7),
            "data-key": "pulse:" + a.kind + ":" + (a.category || "") + ":" + (a.district || "") + ":" + a.target.id,
            text: tr("common.action.show_on_map"),
            onclick: function (e) {
              var ev = new CustomEvent("birge:open-target", { cancelable: true, detail: { target: a.target, days: 7, from: "akim-pulse" } });
              if (!doc.dispatchEvent(ev)) e.preventDefault();
            },
          })
        : null;
      return h("li", { class: "akim-pulse__item", "data-kind": a.kind }, [
        h("span", { class: "akim-pulse__title", text: title }),
        h("span", { class: "akim-pulse__reason bk-meta", text: reason }),
        link,
      ]);
    }
    function d0() {
      return state.data;
    }
    function renderPulse(d) {
      var p = d.pulse;
      if (!p || !p.available) return null;
      var items = p.items || [];
      if (!items.length) {
        // Нет тревог — одна строка мелко, без пустой карточки (IA_WAVE2 §5).
        return h("p", { class: "akim-pulse-none bk-meta" }, [h("strong", { text: tr("akim.pulse.title") + ": " }), tr("akim.pulse.none")]);
      }
      var card = h("section", { class: "bk-card akim-card akim-pulse", "aria-labelledby": "akim-pulse-title" }, [
        h("h2", { class: "bk-h2", id: "akim-pulse-title", text: tr("akim.pulse.title") }),
      ]);
      var first = h("ul", { class: "akim-pulse__list" });
      items.slice(0, 3).forEach(function (a) {
        first.appendChild(pulseRow(a));
      });
      card.appendChild(first);
      if (items.length > 3) {
        var rest = h("ul", { class: "akim-pulse__list" });
        items.slice(3).forEach(function (a) {
          rest.appendChild(pulseRow(a));
        });
        card.appendChild(
          h("details", { class: "bk-details akim-pulse__more" }, [h("summary", { text: tr("akim.pulse.more", { n: items.length - 3 }) }), rest])
        );
      }
      return card;
    }

    function cardHead(titleKey, hintKey, extra) {
      return h("div", { class: "akim-card__head" }, [
        h("h2", { class: "bk-h2", text: tr(titleKey) }),
        extra || null,
        hintKey ? h("p", { class: "akim-card__hint bk-meta", text: tr(hintKey) }) : null,
      ]);
    }
    function unavailable() {
      return h("div", { class: "akim-unavailable" }, [icon("alert"), h("span", { text: tr("akim.unavailable") })]);
    }
    function emptyBlock(key, iconName) {
      return h("div", { class: "bk-empty akim-empty" }, [icon(iconName || "check", 48), h("p", { class: "bk-empty__title", text: tr(key) })]);
    }

    // ── горячие места ──
    function mapLink(target, days) {
      return opts.mapHref
        .replace("{kind}", encodeURIComponent(target.kind))
        .replace("{id}", encodeURIComponent(target.id))
        .replace("{days}", String(days));
    }
    function renderHot(d) {
      var card = h("section", { class: "bk-card akim-card akim-hot", "aria-labelledby": "akim-hot-title" }, [cardHead("akim.hot.title", "akim.hot.hint")]);
      card.firstChild.firstChild.id = "akim-hot-title";
      if (!d.hot.available) {
        card.appendChild(unavailable());
        return card;
      }
      if (!d.hot.items.length) {
        card.appendChild(emptyBlock("akim.hot.empty"));
        return card;
      }
      var list = h("ol", { class: "bk-list akim-hot__list" });
      d.hot.items.forEach(function (it) {
        // Подписи нет (новая цель без названия) — вид места из словаря R11, а не пустая строка.
        var name = label(it.target, "label") || (I() && I().has("heat.kind." + it.target.kind) ? tr("heat.kind." + it.target.kind) : "");
        // Волна мелочей п. 12: не просто «Дороги», а что именно — уточнение, которое чаще всего выбрали жители.
        var what = it.subtopic && it.subtopic.id ? tr("subtopic." + it.subtopic.id) : it.category ? I().cat(it.category) : null;
        var sub = [what, it.district ? tr("district." + it.district) : null].filter(Boolean).join(" · ");
        var a = h(
          "a",
          {
            class: "bk-list__item akim-hot__item",
            "data-key": "hot:" + it.target.kind + ":" + it.target.id,
            href: mapLink(it.target, d.hot.days),
            "aria-label": tr("akim.hot.open", { name: name }) + ". " + tr("common.people", { n: it.count }),
            onclick: function (e) {
              var ev = new CustomEvent("birge:open-target", { cancelable: true, detail: { target: it.target, days: d.hot.days, from: "akim" } });
              if (!doc.dispatchEvent(ev)) e.preventDefault(); // оболочка открыла цель сама
            },
          },
          [
            h("span", { class: "akim-hot__rank", "aria-hidden": "true", text: String(it.rank) }),
            h("span", { class: "bk-heat", "data-level": String(it.level), "aria-hidden": "true", text: num(it.count) }),
            h("span", { class: "bk-list__main" }, [
              h("span", { class: "bk-list__title", text: name }),
              h("span", { class: "bk-list__sub akim-hot__sub" }, [
                sub,
                it.status && it.status !== "new" ? h("span", { class: "bk-status", "data-status": it.status, text: tr("status." + it.status) }) : null,
                it.approximate ? h("span", { class: "bk-tag bk-tag--approx", text: tr("common.tag.approx") }) : null,
              ]),
            ]),
            icon("chevron-right"),
          ]
        );
        list.appendChild(h("li", null, [a]));
      });
      card.appendChild(list);
      return card;
    }

    // ── темы и районы ──
    function bars(rows, opts2) {
      var max = rows.reduce(function (m, r) {
        return Math.max(m, r.value);
      }, 0);
      var ul = h("ul", { class: "bk-bars akim-bars" });
      rows.forEach(function (r) {
        var width = max ? Math.max(2, Math.round((r.value / max) * 100)) : 0;
        var inner = [
          h("span", { class: "bk-bar__label" }, [r.icon ? icon(r.icon, 18) : null, h("span", { text: r.name }), r.badge || null]),
          h("span", { class: "bk-bar__track", "aria-hidden": "true" }, [h("span", { class: "bk-bar__fill", style: "width:" + width + "%" })]),
          h("span", { class: "bk-bar__value", text: num(r.value) }),
        ];
        if (opts2 && opts2.onPick) {
          ul.appendChild(
            h("li", null, [
              h(
                "button",
                {
                  type: "button",
                  class: "bk-bar akim-bar-btn",
                  "data-key": "district:" + r.id,
                  "aria-pressed": r.selected ? "true" : "false",
                  "aria-label": tr("akim.districts.pick", { name: r.name }) + ": " + tr("common.people", { n: r.value }),
                  onclick: function () {
                    opts2.onPick(r.id);
                  },
                },
                inner
              ),
            ])
          );
        } else {
          ul.appendChild(h("li", { class: "bk-bar" }, inner));
        }
      });
      return ul;
    }
    function renderTopics(d) {
      var card = h("section", { class: "bk-card akim-card akim-topics" }, [cardHead("akim.topics.title", "akim.topics.hint")]);
      if (!d.topics.available) card.appendChild(unavailable());
      else if (!d.topics.items.length) card.appendChild(emptyBlock("akim.topics.empty"));
      else
        card.appendChild(
          bars(
            d.topics.items.map(function (t) {
              return { name: I().cat(t.category), value: t.value, icon: t.icon };
            })
          )
        );
      return card;
    }
    function renderDistricts(d) {
      var card = h("section", { class: "bk-card akim-card akim-districts" }, [cardHead("akim.districts.title", "akim.districts.hint")]);
      if (!d.districts.available) {
        card.appendChild(unavailable());
        return card;
      }
      card.appendChild(
        bars(
          d.districts.items.map(function (r) {
            var selected = d.districts.selected === r.district;
            return {
              id: r.district,
              name: tr("district." + r.district),
              value: r.value,
              selected: selected,
              badge: selected ? h("span", { class: "bk-tag akim-selected", text: tr("akim.districts.selected") }) : null,
            };
          }),
          {
            onPick: function (id) {
              setDistrict(state.district === id ? null : id);
            },
          }
        )
      );
      return card;
    }

    // ── объекты (R06) ──
    function objectRow(o) {
      var tags = [];
      if (o.delay_days > 0) tags.push(h("span", { class: "bk-tag bk-tag--warn", text: tr("object.late", { n: o.delay_days }) }));
      if (o.stale && o.days_since_update != null)
        tags.push(h("span", { class: "bk-tag akim-stale", text: tr("object.stale_days", { n: o.days_since_update }) }));
      var title = label(o, "title", "object.kind.");
      var main = [h("span", { class: "bk-list__title", text: title })];
      if (o.district) main.push(h("span", { class: "bk-list__sub", text: tr("district." + o.district) }));
      main.push(stagesEl(o));
      var inner = [h("span", { class: "bk-list__main" }, main), h("span", { class: "akim-obj__tags" }, tags)];
      // Нет места на карте или оболочка не умеет показать объект — обычная строка.
      if (!opts.objectHref || !o.has_place || !o.id) return h("li", { class: "akim-obj" }, inner);
      // R11 (ночь 6, п. 4): строка нажимается, как «Горячие места», — карта с карточкой объекта и этапами.
      inner.push(icon("chevron-right"));
      return h("li", null, [
        h(
          "a",
          {
            class: "akim-obj akim-obj--link",
            "data-key": "object:" + o.id,
            href: opts.objectHref.replace("{id}", encodeURIComponent(o.id)),
            "aria-label": tr("akim.hot.open", { name: title }),
            onclick: function (e) {
              var ev = new CustomEvent("birge:open-object", { cancelable: true, detail: { id: o.id, from: "akim" } });
              if (!doc.dispatchEvent(ev)) {
                e.preventDefault(); // оболочка открыла объект сама
                return;
              }
              // Оболочка R01 разбирает #object=<id> (выбор на карте), но раздел «Картина дня» сама не закрывает.
              if (root.BirgeShell && typeof root.BirgeShell.setSection === "function") root.BirgeShell.setSection("map");
            },
          },
          inner
        ),
      ]);
    }
    // Полоса 6 этапов ui-kit (.bk-stages--compact) + «Этап 4 из 6: Строительство» — как в макете day.html.
    function stagesEl(o) {
      var at = STAGES.indexOf(o.stage);
      if (at < 0) return o.stage ? h("span", { class: "bk-list__sub", text: tr("akim.late.stage", { name: tr("stage." + o.stage) }) }) : null;
      var caption = tr("stage.caption", { i: at + 1, total: STAGES.length, name: tr("stage." + o.stage) });
      return h("span", { class: "akim-obj__stages" }, [
        h(
          "ol",
          { class: "bk-stages bk-stages--compact" + (o.delay_days > 0 ? " bk-stages--late" : ""), "aria-hidden": "true" },
          // Точки без скрытых подписей: полоса только для глаз (aria-hidden), этап словами — в подписи ниже.
          STAGES.map(function (st, i) {
            return h("li", { "data-state": i < at ? "done" : i === at ? "current" : "todo" });
          })
        ),
        h("span", { class: "bk-stages__caption", text: caption }),
      ]);
    }
    function renderObjects(d) {
      var o = d.objects || {};
      var card = h("section", { class: "bk-card akim-card akim-objects" }, [cardHead("akim.late.title", null)]);
      if (!o.available) {
        card.appendChild(unavailable());
        return card;
      }
      // Нет ни одного объекта в реестре (район без работ) — «Пока пусто», а не «Все объекты идут по графику».
      if (!o.total) card.appendChild(emptyBlock("common.state.empty_title", "building"));
      else if (!o.late.length) card.appendChild(emptyBlock("akim.late.empty"));
      else {
        var ul = h("ul", { class: "bk-list akim-obj__list" });
        o.late.slice(0, LATE_VISIBLE).forEach(function (x) {
          ul.appendChild(objectRow(x));
        });
        card.appendChild(ul);
      }
      var lateIds = o.late.slice(0, LATE_VISIBLE).map(function (x) {
        return x.id;
      });
      var staleOnly = o.stale.filter(function (x) {
        return lateIds.indexOf(x.id) < 0;
      });
      if (staleOnly.length) {
        card.appendChild(h("h3", { class: "akim-card__sub", text: tr("akim.late.stale_title") }));
        var ul2 = h("ul", { class: "bk-list akim-obj__list" });
        staleOnly.slice(0, LATE_VISIBLE).forEach(function (x) {
          ul2.appendChild(objectRow(x));
        });
        card.appendChild(ul2);
      }
      return card;
    }

    // ── предложения и голоса (R06) ──
    function renderProposals(d) {
      var p = d.proposals || {};
      var card = h("section", { class: "bk-card akim-card akim-proposals" }, [cardHead("akim.proposals.title", null)]);
      if (!p.available) {
        card.appendChild(unavailable());
        return card;
      }
      if (!p.top.length) {
        card.appendChild(emptyBlock("akim.proposals.empty", "building"));
        return card;
      }
      card.appendChild(h("p", { class: "akim-proposals__new", text: tr("akim.proposals.new", { n: p.new_count }) }));
      var ul = h("ul", { class: "bk-list akim-obj__list" });
      p.top.forEach(function (x) {
        ul.appendChild(
          h("li", { class: "akim-obj" }, [
            h("span", { class: "bk-list__main" }, [
              h("span", { class: "bk-list__title" }, [
                label(x, "title", "proposal.kind."),
                x.is_new ? h("span", { class: "bk-tag bk-tag--project akim-new", text: tr("akim.proposals.new_badge") }) : null,
              ]),
              h("span", { class: "bk-list__sub", text: tr("akim.proposals.votes", { up: x.votes_up, down: x.votes_down }) }),
            ]),
          ])
        );
      });
      card.appendChild(ul);
      return card;
    }

    function renderOk(d) {
      if (d.complaints_available === false) {
        // Нет источника жалоб: показываем это прямо, а не четыре нуля.
        body.appendChild(h("div", { class: "akim-unavailable akim-no-complaints", role: "status" }, [icon("alert"), h("span", { text: tr("akim.no_complaints") })]));
      } else {
        body.appendChild(renderKpis(d));
      }
      body.appendChild(
        h("section", { class: "bk-card akim-card akim-summary", "aria-labelledby": "akim-summary-title" }, [
          h("h2", { class: "akim-summary__title", id: "akim-summary-title", text: tr("akim.summary.title") }),
          summaryText(d),
        ])
      );
      // Порядок по схеме R11 (IA_WAVE2 §5): KPI → сводка → «Нужно решение акима» → «Пульс» → прежние блоки.
      var decisionsEl = renderDecisions(d);
      if (decisionsEl) body.appendChild(decisionsEl);
      var pulseEl = renderPulse(d);
      if (pulseEl) body.appendChild(pulseEl);
      // Две колонки на ноутбуке: слева «Горячие места» и объекты, справа темы, районы, предложения.
      // На телефоне колонки «растворяются» (display: contents), порядок задаёт CSS order.
      body.appendChild(
        h("div", { class: "akim-grid" }, [
          h("div", { class: "akim-col akim-col--main" }, [renderHot(d), renderObjects(d)]),
          h("div", { class: "akim-col akim-col--side" }, [renderTopics(d), renderDistricts(d), renderProposals(d)]),
        ])
      );
      body.appendChild(
        h("button", { type: "button", class: "bk-btn bk-btn--block akim-print-bottom", onclick: function () { printPage(); } }, [
          icon("print"),
          tr("common.action.print"),
        ])
      );
    }

    // Сводка текстом; фраза о главной проблеме — жирным, чтобы глаз сразу нашёл её.
    function summaryText(d) {
      var textLang = lang() === "kk" ? "kk" : "ru";
      var parts = d.text_parts && d.text_parts[textLang];
      var p = h("p", { class: "akim-summary__text", lang: textLang });
      if (!parts || !parts.length) {
        p.textContent = (d.text && (d.text[textLang] || d.text.ru)) || "";
        return p;
      }
      parts.forEach(function (part, i) {
        if (i) p.appendChild(doc.createTextNode(" "));
        p.appendChild(h(part.role === "main" ? "strong" : "span", { class: "akim-summary__" + part.role, text: part.text }));
      });
      return p;
    }

    function render() {
      renderTop();
      body.textContent = "";
      body.setAttribute("aria-busy", state.status === "loading" ? "true" : "false");
      if (state.status === "loading") renderLoading();
      else if (state.status === "error") renderError();
      else renderOk(state.data);
      rootEl.setAttribute("data-state", state.status);
    }

    // ── печать ──
    // В оболочке R01 «Картина дня» — прокручиваемая панель фиксированной высоты поверх карты: браузер напечатал бы
    // только видимую часть и шапку с картой. Перед печатью помечаем свою ветку DOM (от элемента до body), а печатные
    // стили akim.css прячут всё остальное и снимают ограничения высоты. После печати метки снимаются.
    var openedForPrint = [];
    function preparePrint() {
      if (!rootEl.isConnected || !rootEl.getClientRects().length) return; // экран скрыт — печатает тот, кто на виду
      // На бумаге «Ещё N тревог» не раскрыть — раскрываем перед печатью и сворачиваем после.
      Array.prototype.forEach.call(rootEl.querySelectorAll("details:not([open])"), function (el) {
        el.open = true;
        openedForPrint.push(el);
      });
      doc.documentElement.classList.add("akim-printing");
      for (var el = rootEl.parentElement; el && el !== doc.documentElement; el = el.parentElement) el.classList.add("akim-print-path");
    }
    function cleanupPrint() {
      openedForPrint.splice(0).forEach(function (el) {
        el.open = false;
      });
      doc.documentElement.classList.remove("akim-printing");
      Array.prototype.forEach.call(doc.querySelectorAll(".akim-print-path"), function (el) {
        el.classList.remove("akim-print-path");
      });
    }
    function printPage() {
      preparePrint();
      root.print();
    }
    root.addEventListener("beforeprint", preparePrint); // Ctrl+P тоже
    root.addEventListener("afterprint", cleanupPrint);

    var off = null;
    (I() ? I().ready : Promise.resolve())
      .then(function () {
        // Подписка на смену языка — после загрузки словаря, иначе первый кадр покажет ключи.
        if (I()) off = I().onChange(render);
        syncUrl();
        load();
      });

    var handle = {
      reload: load,
      setDate: setDate,
      setDistrict: setDistrict,
      get state() {
        return { date: state.date, district: state.district, status: state.status };
      },
      print: printPage,
      refresh: function () {
        load(true);
      },
      destroy: function () {
        if (off) off();
        if (refreshTimer) clearInterval(refreshTimer);
        doc.removeEventListener("visibilitychange", onVisible);
        root.removeEventListener("beforeprint", preparePrint);
        root.removeEventListener("afterprint", cleanupPrint);
        cleanupPrint();
        state.request++;
        rootEl.textContent = "";
        delete rootEl.birgeAkim;
      },
    };
    rootEl.birgeAkim = handle; // для оболочки и тестов: document.getElementById("akim").birgeAkim.refresh()
    return handle;
  }

  root.BirgeAkim = { mount: mount, version: "akim-r14-w2" };
})(window);
