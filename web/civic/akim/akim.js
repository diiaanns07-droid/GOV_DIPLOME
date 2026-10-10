/*
 * Birge · «Картина дня» для акима (R08, раунд 14).
 *
 * Подключение (после ui-kit и i18n):
 *   <link rel="stylesheet" href="/civic/akim/akim.css">
 *   <script src="/civic/i18n/i18n.js"></script>
 *   <script src="/civic/akim/akim.js"></script>
 *   BirgeAkim.mount(document.getElementById("akim"), { apiBase: "/api/civic/v2" });
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
 */
(function (root) {
  "use strict";

  var DEFAULTS = {
    apiBase: "/api/civic/v2",
    mapHref: "/#target={kind}:{id}&days={days}",
    syncUrl: true, // хранить дату и район в адресе: F5, печать и ссылка показывают то же
  };
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
  function tr(key, params) {
    var i18n = I();
    return i18n ? i18n.t(key, params) : interpolate(key, params);
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

    function load() {
      var id = ++state.request;
      state.status = "loading";
      render();
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
          if (res.ok && res.body && res.body.kpi) {
            state.status = "ok";
            state.data = res.body;
          } else {
            state.status = "error";
            state.error = res.status === 400 && res.body && res.body.field === "date" ? "date" : "server";
          }
        })
        .catch(function () {
          if (id !== state.request) return;
          state.status = "error";
          state.error = "network";
        })
        .then(function () {
          clearTimeout(timer);
          if (id === state.request) render();
        });
    }

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
        h("h1", { class: "akim__title" }, [
          tr("akim.title"),
          h("span", { class: "akim__title-date", text: " · " + I().formatDate(date) }),
          // Метка «Пример» — одна на страницу, здесь; в карточках её нет (UX_REVIEW день 3, п. 11).
          d && state.status === "ok" && d.demo && d.demo.any ? demoTag() : null,
        ]),
        h("p", { class: "akim__meta bk-meta", text: meta.join(" · ") }),
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
              root.print();
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
        kpiCard("overdue", k.overdue, "akim.kpi.overdue", false, [tr("akim.kpi.overdue_hint")]),
        kpiCard("fixed", k.fixed_week, "akim.kpi.fixed_week", true, [tr("akim.kpi.fixed_hint")]),
      ]);
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
        var name = label(it.target, "label");
        var sub = [it.category ? I().cat(it.category) : null, it.district ? tr("district." + it.district) : null].filter(Boolean).join(" · ");
        var a = h(
          "a",
          {
            class: "bk-list__item akim-hot__item",
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
      var main = [h("span", { class: "bk-list__title", text: label(o, "title", "object.kind.") })];
      if (o.district) main.push(h("span", { class: "bk-list__sub", text: tr("district." + o.district) }));
      main.push(stagesEl(o));
      return h("li", { class: "akim-obj" }, [h("span", { class: "bk-list__main" }, main), h("span", { class: "akim-obj__tags" }, tags)]);
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
      if (!o.late.length) card.appendChild(emptyBlock("akim.late.empty"));
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
      if (d.demo && d.demo.any) {
        body.appendChild(h("p", { class: "akim-demo", text: tr("common.tag.demo") + ": " + lowerFirst(tr("akim.demo_note")) }));
      }
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
      // Две колонки на ноутбуке: слева «Горячие места» и объекты, справа темы, районы, предложения.
      // На телефоне колонки «растворяются» (display: contents), порядок задаёт CSS order.
      body.appendChild(
        h("div", { class: "akim-grid" }, [
          h("div", { class: "akim-col akim-col--main" }, [renderHot(d), renderObjects(d)]),
          h("div", { class: "akim-col akim-col--side" }, [renderTopics(d), renderDistricts(d), renderProposals(d)]),
        ])
      );
      body.appendChild(
        h("button", { type: "button", class: "bk-btn bk-btn--block akim-print-bottom", onclick: function () { root.print(); } }, [
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

    var off = null;
    (I() ? I().ready : Promise.resolve())
      .then(function () {
        // Подписка на смену языка — после загрузки словаря, иначе первый кадр покажет ключи.
        if (I()) off = I().onChange(render);
        syncUrl();
        load();
      });

    return {
      reload: load,
      setDate: setDate,
      setDistrict: setDistrict,
      get state() {
        return { date: state.date, district: state.district, status: state.status };
      },
      destroy: function () {
        if (off) off();
        state.request++;
        rootEl.textContent = "";
      },
    };
  }

  root.BirgeAkim = { mount: mount, version: "akim-r14-2" };
})(window);
