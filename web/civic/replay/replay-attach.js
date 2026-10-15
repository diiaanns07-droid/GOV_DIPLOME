/*
 * R07 · «Хроника города» — лёгкий вход (раунд 15, R10 B-113: первый значок карты ≤ 3 с).
 *
 * На первый кадр карты хроника не нужна. Оболочка может подключить вместо replay.js + replay.css только этот файл
 * (≈ 7 КБ с комментариями) и сделать тот же вызов, что у полной хроники (INTEGRATION §1.3):
 *   <script src="/civic/replay/replay-attach.js"></script>
 *   BirgeReplay.attach({ map, heat, tools })
 * Кнопка-часы, ?replay=7|30 (&autoplay=0), событие birge:replay-open и Ctrl+K (heat.commands) работают сразу.
 * replay.css и replay.js (из той же папки) загружаются при первом открытии — или раньше, когда карта уже нарисована и
 * браузер свободен (requestIdleCallback), или при наведении на кнопку. Дальше всё делает полная хроника: она заменяет
 * window.BirgeReplay своим объектом. Если полная хроника уже на странице (стенд R07), этот файл ничего не делает.
 */
(function () {
  "use strict";
  if (window.BirgeReplay && typeof window.BirgeReplay.mount === "function") return;

  const script = document.currentScript;
  const base = script && script.src ? script.src.replace(/[^/]*$/, "") : "/civic/replay/";
  // Запасные подписи кнопки — те же, что в replay.js; в оболочке берутся из словаря R11 (replay.open, replay.open_hint)
  const TEXT = {
    ru: { "replay.open": "Хроника города", "replay.open_hint": "Неделя за 10 секунд", "replay.error": "Не удалось загрузить хронику" },
    kk: { "replay.open": "Қала шежіресі", "replay.open_hint": "Бір апта 10 секундта", "replay.error": "Шежірені жүктеу мүмкін болмады" },
  };
  const CLOCK = '<svg class="rp-ic" viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false" fill="none" ' +
    'stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.2 2"/></svg>';

  const lang = () => (window.Birge && window.Birge.i18n ? window.Birge.i18n.lang() : document.documentElement.lang === "kk" ? "kk" : "ru");
  function text(key) {
    const g = window.Birge && window.Birge.i18n;
    if (g && typeof g.has === "function" && g.has(key, lang())) return g.t(key, {}, lang());
    return (TEXT[lang()] || TEXT.ru)[key] || TEXT.ru[key];
  }
  const full = () => (window.BirgeReplay && typeof window.BirgeReplay.mount === "function" ? window.BirgeReplay : null);

  let loading = null;
  function load() {
    if (full()) return Promise.resolve(full());
    if (loading) return loading;
    loading = new Promise((resolve, reject) => {
      if (!document.querySelector('link[href$="/replay/replay.css"], link[data-rp-css]')) {
        const css = document.createElement("link");
        css.rel = "stylesheet";
        css.href = base + "replay.css";
        css.dataset.rpCss = "1";
        document.head.append(css);
      }
      const js = document.createElement("script");
      js.src = base + "replay.js";
      js.async = true;
      js.onload = () => (full() ? resolve(full()) : reject(new Error("replay.js")));
      js.onerror = () => reject(new Error("replay.js"));
      document.head.append(js);
    }).catch((err) => {
      loading = null;   // следующее нажатие попробует ещё раз
      if (window.BirgeUI && typeof window.BirgeUI.toast === "function") window.BirgeUI.toast(text("replay.error"), { type: "error" });
      throw err;
    });
    return loading;
  }

  function heatHandle(o) {
    if (o.heat && o.heat.replay) return o.heat;
    const shell = window.CivicShell && window.CivicShell.heat;
    if (shell && shell.replay) return shell;
    const cur = window.CivicHeat && window.CivicHeat.current;
    return cur && cur.replay ? cur : null;
  }
  function open(options) {
    return load().then((R) => R.open(options || {}));
  }

  function attach(options) {
    const o = options || {};
    let button = null;
    const tools = typeof o.tools === "string" ? document.querySelector(o.tools) : o.tools;
    if (tools && !tools.querySelector(".rp-open")) {
      button = document.createElement("button");
      button.type = "button";
      button.className = "icon-btn rp-open bk-glass--control";
      const ui = window.BirgeUI;
      button.innerHTML = ui && typeof ui.icon === "function"
        ? '<span class="rp-ic rp-ic--sprite" style="width:22px;height:22px;display:inline-grid;place-items:center" aria-hidden="true">' +
          ui.icon("clock").replace("<svg ", '<svg style="width:22px;height:22px" ') + "</span>"
        : CLOCK;
      const label = () => { button.title = text("replay.open") + " · " + text("replay.open_hint"); button.setAttribute("aria-label", button.title); };
      label();
      button.addEventListener("click", () => {
        const R = full();
        if (R && R.active) { R.active.close(); return; }
        void open({ map: o.map, heat: o.heat || (window.CivicShell && window.CivicShell.heat), days: 7 }).catch(() => {});
      });
      // Наведение или фокус на кнопке — хронику начинаем грузить заранее, чтобы нажатие открыло её сразу
      const warm = () => { void load().catch(() => {}); };
      button.addEventListener("pointerenter", warm, { once: true });
      button.addEventListener("focus", warm, { once: true });
      document.addEventListener("birge:lang", label);
      window.addEventListener("birge:lang", label);
      tools.append(button);
    }
    const p = new URLSearchParams(location.search);
    const days = Number(p.get("replay"));
    let tries = 0;
    const whenReady = (fn) => {
      const heat = heatHandle(o);
      if (heat && heat.state && heat.state().status === "ready") fn(heat);
      else if (++tries < 100) setTimeout(() => whenReady(fn), 200);
    };
    if (days === 7 || days === 30) {
      // ?replay=7 — открыть, как только тепловая карта загрузит «сегодня» (иначе хронике нечего вернуть после закрытия)
      whenReady((heat) => { void open({ map: o.map, heat, days, autoplay: p.get("autoplay") !== "0" }).catch(() => {}); });
    } else if (typeof window.requestIdleCallback === "function") {
      // Карта нарисована — хронику подгружаем в свободное время браузера (не раньше 3 с после первого кадра)
      whenReady(() => setTimeout(() => window.requestIdleCallback(() => { void load().catch(() => {}); }, { timeout: 10000 }), 3000));
    }
    // Событие ловит только этот вход: attach полной хроники при ленивой загрузке не вызывается (двойного открытия нет)
    document.addEventListener("birge:replay-open", (ev) => {
      void open(Object.assign({ map: o.map, heat: o.heat }, (ev && ev.detail) || {})).catch(() => {});
    });
    return { button };
  }

  window.BirgeReplay = { attach, open, load, lazy: true, get active() { const R = full(); return R ? R.active : null; } };
})();
