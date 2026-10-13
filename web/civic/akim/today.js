/*
 * Birge · «Сегодня в Астане» — сводка на главной карте акимата (R08, эталон research/round-14/design/REFERENCE.html,
 * вариант A «2ГИС светлый», экран «Главная акимата»): 3 числа (новых · в работе · просрочено) + 3 горячих места +
 * «Все горячие места». Карточка слева под поиском и чипами, закрывается (×, Esc). Место и закрытие — оболочка R01.
 *
 *   BirgeToday.mount(el, { apiBase: "/api/civic/v2", mapHref, onClose, onAllHot }) → { reload, setLang, destroy, el }
 *
 * Данные: GET {apiBase}/akim/summary (тот же ответ, что у «Картины дня» R08: kpi.new_day, kpi.in_progress, kpi.overdue,
 * hot.items[0..2]). Строка места: событие «birge:open-target» (оболочка открывает карточку цели и ведёт карту; не
 * обработано — переход по ссылке mapHref). Наведение и фокус строки: событие «birge:hover-target» {target, on} —
 * карта R07 может подсветить значок (синхронизация список ↔ карта, правило Linear 5). «Все горячие места»:
 * «birge:open-hot-list» (не обработано — раздел #day). Закрыть: opts.onClose(); без него — карточка прячется сама.
 * Клавиатура в карточке: ↑ ↓ (и J K) — по местам, Esc — закрыть. Загрузка: скелет — только если ответ дольше 150 мс.
 */
(function (root) {
  "use strict";
  var doc = root.document;
  var ICONS = ((doc.currentScript && doc.currentScript.src) || "").replace(/[^/]*$/, "") + "../ui-kit/icons.svg";
  var SKELETON_AFTER_MS = 150; // правило Linear 4: быстрый ответ — без мигания скелетом
  var TIMEOUT_MS = 15000;

  // Ключи сводки, которых пока нет в словаре R11 (запас до слияния; список — research/round-14-results/R08/I18N_TODAY.json).
  var KEYS = {
    ru: {
      "akim.today.title": "Сегодня в Астане",
      "akim.today.new": "новых",
      "akim.today.in_progress": "в работе",
      "akim.today.overdue": "просрочено",
      "akim.today.all_hot": "Все горячие места",
      "akim.today.close": "Закрыть сводку",
      "akim.today.error": "Сводка не загрузилась",
    },
    kk: {
      "akim.today.title": "Бүгін Астанада",
      "akim.today.new": "жаңа",
      "akim.today.in_progress": "орындалуда",
      "akim.today.overdue": "мерзімі өткен",
      "akim.today.all_hot": "Барлық шағымы көп орындар",
      "akim.today.close": "Қорытындыны жабу",
      "akim.today.error": "Қорытынды жүктелмеді",
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
  function tr(key, params) {
    var i18n = I();
    if (i18n && (i18n.has(key) || i18n.has(key, "ru"))) return i18n.t(key, params);
    var l = lang() === "kk" ? "kk" : "ru";
    var v = KEYS[l][key] != null ? KEYS[l][key] : KEYS.ru[key];
    if (v != null) return v;
    return i18n ? i18n.t(key, params) : key;
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
  function icon(name, size) {
    var svg = doc.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "ic");
    svg.setAttribute("width", String(size || 18));
    svg.setAttribute("height", String(size || 18));
    svg.setAttribute("aria-hidden", "true");
    var use = doc.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", ICONS + "#i-" + name);
    svg.appendChild(use);
    return svg;
  }
  function placeName(t) {
    var l = lang();
    return (t && (t["label_" + l] || t.label_ru)) || (I() && t && I().has("heat.kind." + t.kind) ? tr("heat.kind." + t.kind) : "");
  }
  function emit(name, detail) {
    var ev = new CustomEvent(name, { cancelable: true, detail: detail });
    return doc.dispatchEvent(ev); // false — оболочка обработала сама (preventDefault)
  }

  function mount(el, options) {
    var opts = Object.assign({ apiBase: "/api/civic/v2", mapHref: "/#target={kind}:{id}&days={days}" }, options || {});
    var state = { status: "loading", data: null, request: 0, skeleton: false };
    el.classList.add("akim-today", "bk-glass"); // стекло и запасной непрозрачный вид — ui-kit R11
    el.setAttribute("role", "region");

    function load() {
      var id = ++state.request;
      if (state.status !== "ok") {
        state.status = "loading";
        state.skeleton = false;
        render();
        setTimeout(function () {
          if (id === state.request && state.status === "loading") {
            state.skeleton = true;
            render();
          }
        }, SKELETON_AFTER_MS);
      }
      var ctrl = typeof AbortController === "function" ? new AbortController() : null;
      var timer = setTimeout(function () {
        if (ctrl) ctrl.abort();
      }, TIMEOUT_MS);
      fetch(opts.apiBase + "/akim/summary", { headers: { Accept: "application/json" }, signal: ctrl ? ctrl.signal : undefined })
        .then(function (r) {
          if (!r.ok) throw new Error("http " + r.status);
          return r.json();
        })
        .then(function (d) {
          if (id !== state.request || !d || !d.kpi) return;
          state.data = d;
          state.status = "ok";
        })
        .catch(function () {
          if (id !== state.request) return;
          if (state.status !== "ok") state.status = "error"; // тихое обновление не меняет числа ошибкой
        })
        .then(function () {
          clearTimeout(timer);
          if (id === state.request) render();
        });
    }

    function close() {
      if (typeof opts.onClose === "function") opts.onClose();
      else el.hidden = true;
      emit("birge:today-close", {});
    }

    function kpi(value, labelKey, kind) {
      return h("div", { class: "akim-today__kpi", "data-kind": kind }, [
        h("b", { text: num(value) }),
        h("span", { text: tr(labelKey) }),
      ]);
    }

    function row(it, days) {
      var name = placeName(it.target);
      var cat = it.category && I() ? I().cat(it.category) : "";
      var href = opts.mapHref
        .replace("{kind}", encodeURIComponent(it.target.kind))
        .replace("{id}", encodeURIComponent(it.target.id))
        .replace("{days}", String(days));
      var hover = function (on) {
        return function () {
          emit("birge:hover-target", { target: it.target, on: on, from: "akim-today" });
        };
      };
      return h("li", null, [
        h(
          "a",
          {
            class: "akim-today__row",
            href: href,
            "data-key": "today:" + it.target.kind + ":" + it.target.id,
            onclick: function (e) {
              if (!emit("birge:open-target", { target: it.target, days: days, from: "akim-today" })) e.preventDefault();
            },
            onmouseenter: hover(true),
            onmouseleave: hover(false),
            onfocus: hover(true),
            onblur: hover(false),
          },
          [
            h("span", { class: "akim-today__cnt", "data-level": String(it.level || 1), "aria-hidden": "true", text: num(it.count) }),
            h("span", { class: "akim-today__place" }, [
              h("span", { class: "akim-today__name", text: name }),
              cat ? h("small", { text: cat }) : null,
            ]),
            h("span", { class: "bk-sr-only", text: " · " + (I() ? I().t("common.people", { n: it.count }) : it.count) }),
          ]
        ),
      ]);
    }

    function render() {
      el.textContent = "";
      el.setAttribute("data-state", state.status);
      el.setAttribute("aria-busy", state.status === "loading" ? "true" : "false");
      var titleId = "akim-today-title";
      el.setAttribute("aria-labelledby", titleId);
      el.appendChild(
        h("div", { class: "akim-today__h" }, [
          h("h2", { id: titleId, text: tr("akim.today.title") }),
          h("button", { type: "button", class: "akim-today__x", "aria-label": tr("akim.today.close"), onclick: close }, [icon("close", 18)]),
        ])
      );
      if (state.status === "loading") {
        if (!state.skeleton) return; // первые 150 мс — без скелета
        el.appendChild(
          h("div", { class: "akim-today__kpis", "aria-hidden": "true" }, [0, 1, 2].map(function () {
            return h("div", { class: "akim-today__kpi" }, [h("span", { class: "bk-skel akim-today__skel-num" }), h("span", { class: "bk-skel akim-today__skel-label" })]);
          }))
        );
        return;
      }
      if (state.status === "error") {
        el.appendChild(
          h("p", { class: "akim-today__error", role: "alert" }, [
            tr("akim.today.error") + " · ",
            h("button", { type: "button", class: "akim-today__retry", onclick: load, text: tr("common.action.retry") }),
          ])
        );
        return;
      }
      var d = state.data;
      var k = d.kpi;
      el.appendChild(
        h("div", { class: "akim-today__kpis" }, [
          kpi(k.new_day.value, "akim.today.new", "new"),
          kpi(k.in_progress.value, "akim.today.in_progress", "in_progress"),
          kpi(k.overdue.value, "akim.today.overdue", "overdue"),
        ])
      );
      var items = (d.hot && d.hot.available && d.hot.items) || [];
      if (items.length) {
        var list = h("ol", { class: "akim-today__hot", "aria-label": tr("akim.hot.title") });
        items.slice(0, 3).forEach(function (it) {
          list.appendChild(row(it, d.hot.days || 7));
        });
        el.appendChild(list);
        el.appendChild(
          h("a", {
            class: "akim-today__more",
            href: "#day",
            text: tr("akim.today.all_hot"),
            onclick: function (e) {
              if (!emit("birge:open-hot-list", { from: "akim-today" })) e.preventDefault();
            },
          })
        );
      }
    }

    // ↑ ↓ / J K — по местам; Esc — закрыть (правило Linear 2: клавиатура).
    function onKey(e) {
      if (e.key === "Escape") {
        e.stopPropagation();
        close();
        return;
      }
      var rows = Array.prototype.slice.call(el.querySelectorAll(".akim-today__row"));
      if (!rows.length) return;
      var down = e.key === "ArrowDown" || e.key === "j" || e.key === "J";
      var up = e.key === "ArrowUp" || e.key === "k" || e.key === "K";
      if (!down && !up) return;
      var i = rows.indexOf(doc.activeElement);
      e.preventDefault();
      var next = i < 0 ? (down ? 0 : rows.length - 1) : (i + (down ? 1 : rows.length - 1)) % rows.length;
      rows[next].focus();
    }
    el.addEventListener("keydown", onKey);

    var off = null;
    var onVisible = function () {
      if (doc.visibilityState === "visible" && state.status === "ok") load();
    };
    doc.addEventListener("visibilitychange", onVisible);
    render();
    (I() ? I().ready : Promise.resolve()).then(function () {
      if (I()) off = I().onChange(render);
      load();
    });
    return {
      el: el,
      reload: load,
      setLang: render,
      open: function () {
        el.hidden = false;
      },
      destroy: function () {
        if (off) off();
        state.request++;
        el.removeEventListener("keydown", onKey);
        doc.removeEventListener("visibilitychange", onVisible);
        el.textContent = "";
      },
    };
  }

  root.BirgeToday = { mount: mount, version: "akim-today-ref-a" };
})(window);
