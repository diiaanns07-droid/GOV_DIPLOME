/*
 * Birge · «Прогноз на неделю: где вероятнее рост жалоб» (R13, раунд 15) — готовый блок для «Картины дня» и
 * Ситуационного центра R08 (IDEA §5: кейс Gton «Предиктивная аналитика»). ПРОТОТИП: история жалоб — синтетика,
 * погода — реальная (Open-Meteo); пометка «прототип» и «Как считаем» с числами проверки — всегда на экране.
 *
 *   <script src="/civic/meetings/forecast-week.js"></script>
 *   BirgeForecastWeek.mount(element, { api, apiBase, district, openTarget, titleTag }) → { setLang, refresh, destroy }
 *   BirgeForecastWeek.render(element, week, opts)  — нарисовать уже полученные данные (akim/board → week)
 *
 * Данные: GET /api/civic/v2/forecast?k=5[&district=] → поле week (ui/civic_forecast.week_block, R13).
 * Числа считает код R13; блок только показывает их. Стили — ui-kit (bk-card, bk-tag, bk-details) + свои fw-*.
 */
(function (root) {
  "use strict";

  const doc = root.document;
  const KEYS = {
    ru: {
      title: "Прогноз на неделю: где вероятнее рост жалоб", prototype: "прототип", how: "Как считаем",
      high: "высокий риск", medium: "средний риск", low: "низкий риск", on_map: "На карте",
      empty: "Прогноза на эту неделю пока нет.", error: "Прогноз сейчас недоступен.", retry: "Повторить",
      period: "{from} — {to}", weather: "Сезон (норма прошлых лет)", loading: "Загружаем прогноз…",
      top10: "Точность первых 10", base: "«как в прошлом месяце»",
    },
    kk: {
      title: "Апталық болжам: шағым қай жерде көбеюі мүмкін", prototype: "прототип", how: "Қалай есептейміз",
      high: "жоғары тәуекел", medium: "орташа тәуекел", low: "төмен тәуекел", on_map: "Картада",
      empty: "Осы аптаға болжам әзірге жоқ.", error: "Болжам қазір қолжетімсіз.", retry: "Қайталау",
      period: "{from} — {to}", weather: "Маусым (өткен жылдардың нормасы)", loading: "Болжам жүктелуде…",
      top10: "Алғашқы 10-ның дәлдігі", base: "«өткен айдағыдай»",
    },
  };
  const MONTHS = { ru: ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"],
    kk: ["қаң", "ақп", "нау", "сәу", "мам", "мау", "шіл", "там", "қыр", "қаз", "қар", "жел"] };
  const DISTRICTS = { ru: { almaty: "Алматы", baikonur: "Байконур", esil: "Есиль", nura: "Нура", saraishyk: "Сарайшык", saryarka: "Сарыарка" },
    kk: { almaty: "Алматы", baikonur: "Байқоңыр", esil: "Есіл", nura: "Нұра", saraishyk: "Сарайшық", saryarka: "Сарыарқа" } };
  const lang = () => (root.BirgeI18n && typeof root.BirgeI18n.getLang === "function" && root.BirgeI18n.getLang() === "kk" ? "kk" : "ru");
  const t = (key, params) => String(KEYS[lang()][key] || KEYS.ru[key] || key).replace(/\{(\w+)\}/g, (w, n) => (params && params[n] != null ? params[n] : w));
  const day = (iso) => { const [, m, d] = String(iso || "").split("-").map(Number); return d && m ? d + " " + MONTHS[lang()][m - 1] : "—"; };
  const pct = (v) => (typeof v === "number" ? Math.round(v * 100) + " %" : "—");
  function h(tag, attrs, children) {
    const el = doc.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === "text") el.textContent = v; else if (k === "class") el.className = v;
      else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : v);
    }
    for (const c of children || []) if (c != null && c !== false) el.appendChild(typeof c === "string" ? doc.createTextNode(c) : c);
    return el;
  }

  function render(el, week, opts) {
    opts = opts || {};
    const l = lang();
    const box = h("section", { class: "fw bk-card", "aria-labelledby": "fw-title", "data-evidence": week && week.evidence_type });
    box.appendChild(h("div", { class: "fw__hd" }, [
      h(opts.titleTag || "h3", { class: "fw__title", id: "fw-title", text: (week && week["title_" + l]) || t("title") }),
      h("span", { class: "bk-tag bk-tag--warn fw__tag", title: week && week["note_" + l], text: t("prototype") }),
    ]));
    if (!week || !week.items || !week.items.length) {
      box.appendChild(h("p", { class: "fw__empty", text: t("empty") }));
      el.replaceChildren(box);
      return box;
    }
    box.appendChild(h("p", { class: "fw__period", text: t("period", { from: day(week.period.from), to: day(week.period.to) }) + " · " + (week["note_" + l] || "") }));
    // Общая для всех территорий сезонная причина — одной строкой над списком (не пять раз подряд).
    if (week["season_" + l]) box.appendChild(h("p", { class: "fw__season" }, [h("span", { class: "fw__weather-label", text: t("weather") + ": " }), week["season_" + l]]));
    box.appendChild(h("ol", { class: "fw__list" }, week.items.map((item) => {
      const label = (item.target && (item.target["label_" + l] || item.target.label_ru)) || "";
      const canMap = typeof opts.openTarget === "function" && item.target && item.target.kind && item.target.id;
      return h("li", { class: "fw__item", "data-level": item.level }, [
        h("span", { class: "fw__rank", "aria-hidden": "true", text: String(item.rank) }),
        h("div", { class: "fw__main" }, [
          h("p", { class: "fw__label", text: label }),
          h("p", { class: "fw__meta" }, [h("span", { text: DISTRICTS[l][item.district] || item.district || "" }),
            h("span", { class: "fw__level fw__level--" + item.level, text: t(item.level) })]),
          item["reason_" + l] ? h("p", { class: "fw__reason", text: item["reason_" + l] }) : null,
          item["weather_" + l] ? h("p", { class: "fw__weather" }, [h("span", { class: "fw__weather-label", text: t("weather") + ": " }),
            item["weather_" + l]]) : null,
        ]),
        canMap ? h("button", { type: "button", class: "fw__map bk-btn bk-btn--ghost", onclick: () => opts.openTarget(item.target.kind, item.target.id),
          text: t("on_map") }) : null,
      ]);
    })));
    const m = week.method || {};
    const b = m.backtest || {};
    box.appendChild(h("details", { class: "fw__how bk-details" }, [
      h("summary", { text: t("how") }),
      h("p", { text: m["text_" + l] || "" }),
      h("p", { class: "fw__nums" }, [h("b", { text: pct(b.precision_at_10) }), " " + t("top10") + " · " + t("base") + " — " + pct(b.baseline_last_month_at_10)]),
    ]));
    el.replaceChildren(box);
    return box;
  }

  function mount(el, options) {
    const opts = Object.assign({ apiBase: "/api/civic/v2" }, options || {});
    let alive = true, last = null, timer = null, shown = lang();
    const call = (path) => (opts.api && typeof opts.api.v2 === "function" ? opts.api.v2("GET", path)
      : root.fetch(opts.apiBase + path, { credentials: "same-origin", headers: { Accept: "application/json" } })
        .then((r) => (r.ok ? r.json() : Promise.reject({ status: r.status }))));
    function load() {
      clearTimeout(timer);
      timer = setTimeout(() => { if (alive && !last) el.replaceChildren(h("p", { class: "fw__loading bk-skel bk-skel--block", role: "status", text: t("loading") })); }, 150);
      const q = "/forecast?k=5" + (opts.district ? "&district=" + encodeURIComponent(opts.district) : "");
      return call(q).then((data) => {
        clearTimeout(timer);
        if (!alive) return;
        last = data && data.week;
        render(el, last, opts);
      }, () => {
        clearTimeout(timer);
        if (!alive) return;
        el.replaceChildren(h("div", { class: "fw bk-card fw--error", role: "status" }, [h("p", { text: t("error") }),
          h("button", { type: "button", class: "bk-btn", onclick: load, text: t("retry") })]));
      });
    }
    const relang = () => { if (shown !== lang()) { shown = lang(); if (last) render(el, last, opts); } };
    const off = root.BirgeI18n && typeof root.BirgeI18n.onChange === "function" ? root.BirgeI18n.onChange(relang) : null;
    load();
    return { setLang: relang, refresh: load, destroy() { alive = false; clearTimeout(timer); if (off) off(); el.replaceChildren(); } };
  }

  // Стили блока — здесь же (блок живёт на экране R08, без отдельного файла CSS).
  if (!doc.getElementById("fw-style")) {
    const style = doc.createElement("style");
    style.id = "fw-style";
    style.textContent = [
      ".fw{display:grid;gap:8px;padding:16px;font-size:15px;line-height:1.45;color:var(--c-ink,#121a17)}",
      ".fw p{margin:0}.fw__hd{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 10px}",
      ".fw__title{margin:0;font-size:15px;font-weight:600}.fw__period,.fw__season,.fw__meta,.fw__reason,.fw__weather,.fw__empty{color:var(--c-text-2,#4b5752);font-size:13px}",
      ".fw__list{display:grid;gap:0;margin:0;padding:0;list-style:none}",
      ".fw__item{display:flex;align-items:flex-start;gap:10px;padding:10px 0;border-top:1px solid var(--c-line,rgba(18,26,23,.08))}",
      ".fw__item:first-child{border-top:0}.fw__rank{flex:none;width:24px;height:24px;border-radius:50%;background:var(--c-fill,rgba(18,26,23,.06));",
      "display:inline-flex;align-items:center;justify-content:center;font-size:13px;font-weight:600;font-variant-numeric:tabular-nums}",
      ".fw__main{display:grid;flex:1;gap:2px;min-width:0}.fw__label{font-weight:600;overflow-wrap:anywhere}",
      ".fw__meta{display:flex;flex-wrap:wrap;gap:4px 8px}.fw__level{font-weight:500}.fw__level--high{color:var(--c-danger,#9a2e28)}",
      ".fw__weather-label{font-weight:500}.fw__map{flex:none;min-height:36px}",  // П1: без эмодзи — подпись словами
      ".fw__how summary{cursor:pointer;font-size:13px;font-weight:600}.fw__how p{margin-top:6px;font-size:13px;color:var(--c-text-2,#4b5752)}",
      ".fw__nums b{color:var(--c-ink,#121a17)}",
    ].join("");
    (doc.head || doc.documentElement).appendChild(style);
  }

  root.BirgeForecastWeek = { mount, render, version: "r13-forecast-week-1" };
})(typeof window !== "undefined" ? window : this);
