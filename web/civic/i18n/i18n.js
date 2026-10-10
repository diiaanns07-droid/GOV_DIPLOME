/*
 * Birge · i18n (R11, раунд 14) — переводы ru / kk без библиотек.
 *
 * Подключение:  <script src="/civic/i18n/i18n.js"></script>
 * Затем:        BirgeI18n.ready.then(() => render());
 *               BirgeI18n.t("complaint.cta")                       → «Сообщить о проблеме»
 *               BirgeI18n.t("common.people", { n: 12 })            → «12 человек» / «12 адам»
 *               BirgeI18n.setLang("kk")                            → переключение + запоминание
 *               BirgeI18n.onChange(lang => render())               → перерисовать модуль
 *               <span data-i18n="common.action.close"></span>       → BirgeI18n.apply(root)
 *               <input data-i18n-attr="placeholder:common.search.placeholder">
 *
 * Правила (UX_SPEC §7):
 *  - словари лежат рядом: ru.json, kk.json; ключи плоские «модуль.экран.что»;
 *  - значение-строка или формы числа {one, few, many, other}; форма выбирается по params.n;
 *  - параметры {name} подставляются, числа форматируются «1 666» (неразрывный пробел);
 *  - нет ключа в kk → берём ru и один раз пишем console.warn; нет и в ru → возвращаем сам ключ
 *    (тест tests/civic/R11 и чек-лист экрана ловят такие места).
 *
 * Работает и в Node (module.exports) — для тестов: init({ dicts: { ru, kk } }) без сети.
 */
(function (root, factory) {
  "use strict";
  var api = factory(root);
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.BirgeI18n = api;
})(typeof self !== "undefined" ? self : this, function (root) {
  "use strict";

  var SUPPORTED = ["ru", "kk"];
  var FALLBACK = "ru";
  var STORAGE_KEY = "birge.lang";
  var NBSP = " ";
  // Время Астаны: с 1 марта 2024 весь Казахстан живёт в UTC+5. Берём фиксированный сдвиг,
  // а не Asia/Almaty: в старых браузерах база часовых поясов может ещё считать UTC+6.
  var ASTANA_OFFSET_MIN = 5 * 60;

  var dicts = { ru: null, kk: null };
  var lang = FALLBACK;
  var listeners = [];
  var warned = {}; // ключи, о которых уже предупредили (по одному разу)
  var missing = {}; // для отчёта: lang → {key: true}
  var baseUrl = "";
  var doc = root && root.document;

  // Папка, из которой загружен скрипт: словари лежат рядом.
  if (doc && doc.currentScript && doc.currentScript.src) {
    baseUrl = doc.currentScript.src.replace(/[^/]*$/, "");
  }

  function warnOnce(id, message) {
    if (warned[id]) return;
    warned[id] = true;
    if (typeof console !== "undefined" && console.warn) console.warn("[i18n] " + message);
  }

  function noteMissing(l, key) {
    (missing[l] = missing[l] || {})[key] = true;
  }

  function normalizeLang(value) {
    var v = String(value || "")
      .toLowerCase()
      .slice(0, 2);
    if (v === "kz") v = "kk"; // частая ошибка: kz — код страны, язык — kk
    return SUPPORTED.indexOf(v) >= 0 ? v : null;
  }

  function readSaved() {
    try {
      return normalizeLang(root.localStorage && root.localStorage.getItem(STORAGE_KEY));
    } catch (e) {
      return null; // приватный режим, file:// и т. п.
    }
  }

  function save(l) {
    try {
      if (root.localStorage) root.localStorage.setItem(STORAGE_KEY, l);
    } catch (e) {
      /* без запоминания — не страшно */
    }
  }

  function fromUrl() {
    try {
      var q = root.location && root.location.search;
      var m = q && q.match(/[?&]lang=([a-zA-Z]{2})/);
      return m ? normalizeLang(m[1]) : null;
    } catch (e) {
      return null;
    }
  }

  function loadDict(l) {
    if (dicts[l]) return Promise.resolve(dicts[l]);
    if (typeof fetch !== "function") return Promise.reject(new Error("fetch недоступен"));
    return fetch(baseUrl + l + ".json", { cache: "no-cache" })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (data) {
        dicts[l] = data;
        return data;
      });
  }

  // ── Склонения ──

  // Форма числа для русского: 1 день, 2 дня, 5 дней; дробные — other.
  function pluralRu(n) {
    var a = Math.abs(n);
    if (a % 1 !== 0) return "other";
    var m10 = a % 10;
    var m100 = a % 100;
    if (m10 === 1 && m100 !== 11) return "one";
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return "few";
    return "many";
  }

  // В казахском существительное после числительного не меняется: «1 адам», «12 адам».
  function pluralCategory(l, n) {
    return l === "ru" ? pluralRu(n) : "other";
  }

  function pickForm(forms, l, n) {
    var cat = pluralCategory(l, Number(n));
    if (forms[cat] != null) return forms[cat];
    // Запасные пути: в kk обычно одна форма other; в ru у дробных — other или few.
    var order = ["other", "many", "few", "one"];
    for (var i = 0; i < order.length; i++) if (forms[order[i]] != null) return forms[order[i]];
    return "";
  }

  // ── Форматы ──

  // 1666 → «1 666», 1234.5 → «1 234,5», −12 → «−12». Одинаково для ru и kk.
  function formatNumber(value, opts) {
    var n = Number(value);
    if (!isFinite(n)) return "—";
    var decimals = opts && opts.decimals != null ? opts.decimals : Math.abs(n % 1) > 0 ? 1 : 0;
    var fixed = Math.abs(n).toFixed(decimals);
    var parts = fixed.split(".");
    var int = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);
    var out = parts[1] && Number(parts[1]) !== 0 ? int + "," + parts[1] : int;
    return (n < 0 && Number(fixed) !== 0 ? "−" : "") + out;
  }

  // 0.4 или 40 → «40 %». opts.fraction=true, если передана доля.
  function formatPercent(value, opts) {
    var n = Number(value);
    if (opts && opts.fraction) n = n * 100;
    return formatNumber(Math.round(n)) + NBSP + "%";
  }

  // Дата в календаре Астаны: {y, m (1–12), d, hh, mm}.
  function astanaParts(input) {
    if (typeof input === "string" && /^\d{4}-\d{2}-\d{2}$/.test(input)) {
      // Просто дата без времени — не сдвигаем по поясу.
      var p = input.split("-");
      return { y: +p[0], m: +p[1], d: +p[2], hh: 0, mm: 0 };
    }
    var t = input instanceof Date ? input.getTime() : Date.parse(input);
    if (!isFinite(t)) return null;
    var local = new Date(t + ASTANA_OFFSET_MIN * 60000);
    return {
      y: local.getUTCFullYear(),
      m: local.getUTCMonth() + 1,
      d: local.getUTCDate(),
      hh: local.getUTCHours(),
      mm: local.getUTCMinutes(),
    };
  }

  function pad2(v) {
    return (v < 10 ? "0" : "") + v;
  }

  // «11 окт», «11 қазан»; год добавляется, если он не текущий (или opts.year=true).
  function formatDate(input, opts) {
    var p = astanaParts(input);
    if (!p) return "—";
    var month = t("dates.month_short." + p.m);
    var now = astanaParts(opts && opts.now ? opts.now : new Date());
    var withYear = (opts && opts.year) || (now && now.y !== p.y);
    return p.d + NBSP + month + (withYear ? NBSP + p.y : "");
  }

  function formatTime(input) {
    var p = astanaParts(input);
    return p ? pad2(p.hh) + ":" + pad2(p.mm) : "—";
  }

  function formatDateTime(input, opts) {
    return formatDate(input, opts) + ", " + formatTime(input);
  }

  // «сегодня», «вчера», «3 дня назад» — по календарным дням Астаны.
  function formatRelative(input, opts) {
    var p = astanaParts(input);
    var now = astanaParts(opts && opts.now ? opts.now : new Date());
    if (!p || !now) return "—";
    var days = Math.round((Date.UTC(now.y, now.m - 1, now.d) - Date.UTC(p.y, p.m - 1, p.d)) / 86400000);
    if (days <= 0) return t("common.time.today");
    if (days === 1) return t("common.time.yesterday");
    if (days < 30) return t("common.time.days_ago", { n: days });
    return formatDate(input, opts);
  }

  // ── Перевод ──

  function lookup(l, key) {
    var d = dicts[l];
    return d && Object.prototype.hasOwnProperty.call(d, key) ? d[key] : undefined;
  }

  function interpolate(text, params, key) {
    if (!params) return text;
    return String(text).replace(/\{(\w+)\}/g, function (whole, name) {
      if (!Object.prototype.hasOwnProperty.call(params, name) || params[name] == null) {
        warnOnce("param:" + key + ":" + name, "нет параметра {" + name + "} для ключа " + key);
        return whole;
      }
      var v = params[name];
      return typeof v === "number" ? formatNumber(v) : String(v);
    });
  }

  // t(key, params, langOverride?) — третий аргумент нужен модулям, которые сами знают язык (R07: Birge.i18n.t).
  function t(key, params, langOverride) {
    var cur = (langOverride && normalizeLang(langOverride) && dicts[normalizeLang(langOverride)]) ? normalizeLang(langOverride) : lang;
    var used = cur;
    var value = lookup(cur, key);
    if (value === undefined && cur !== FALLBACK) {
      value = lookup(FALLBACK, key);
      used = FALLBACK;
      noteMissing(cur, key);
      if (value !== undefined) warnOnce(cur + ":" + key, "нет перевода " + cur + ": " + key + " — показан ru");
    }
    if (value === undefined) {
      noteMissing(FALLBACK, key);
      warnOnce("none:" + key, "неизвестный ключ: " + key);
      return key;
    }
    if (value && typeof value === "object") {
      var n = params && (params.n != null ? params.n : params.count);
      if (n == null) warnOnce("n:" + key, "ключ " + key + " ждёт число {n}");
      value = pickForm(value, used, n == null ? 0 : n);
    }
    return interpolate(value, params, key);
  }

  function has(key, l) {
    return lookup(l || lang, key) !== undefined;
  }

  // Название категории v2 по id из categories_v2.json.
  function cat(id) {
    return t("cat." + id);
  }

  // ── DOM ──

  // data-i18n="key" → textContent; data-i18n-params='{"n":3}';
  // data-i18n-attr="placeholder:key;aria-label:key2;title:key3".
  function apply(rootEl) {
    var scope = rootEl || doc;
    if (!scope || !scope.querySelectorAll) return;
    var nodes = scope.querySelectorAll("[data-i18n],[data-i18n-attr]");
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      var params = null;
      var raw = el.getAttribute("data-i18n-params");
      if (raw) {
        try {
          params = JSON.parse(raw);
        } catch (e) {
          warnOnce("json:" + raw, "неверный data-i18n-params: " + raw);
        }
      }
      var key = el.getAttribute("data-i18n");
      if (key) el.textContent = t(key, params);
      var attrs = el.getAttribute("data-i18n-attr");
      if (attrs) {
        attrs.split(";").forEach(function (pair) {
          var idx = pair.indexOf(":");
          if (idx > 0) el.setAttribute(pair.slice(0, idx).trim(), t(pair.slice(idx + 1).trim(), params));
        });
      }
    }
  }

  function setDocumentLang(l) {
    if (doc && doc.documentElement) doc.documentElement.setAttribute("lang", l);
  }

  function emit() {
    listeners.slice().forEach(function (fn) {
      try {
        fn(lang);
      } catch (e) {
        if (typeof console !== "undefined") console.error(e);
      }
    });
    // Событие и на document, и на window: модули слушают по-разному (R09 — window).
    if (doc && typeof root.CustomEvent === "function") {
      doc.dispatchEvent(new root.CustomEvent("birge:lang", { detail: { lang: lang } }));
      if (typeof root.dispatchEvent === "function") root.dispatchEvent(new root.CustomEvent("birge:lang", { detail: { lang: lang } }));
    }
  }

  function setLang(next) {
    var l = normalizeLang(next);
    if (!l) {
      warnOnce("lang:" + next, "неизвестный язык " + next + ", остаётся " + lang);
      return Promise.resolve(lang);
    }
    return loadDict(l)
      .then(
        function () {
          lang = l;
          save(l); // запоминаем только удачный выбор
        },
        function (err) {
          // Словарь не загрузился (нет связи) — показываем ru, выбор пользователя не перезаписываем.
          warnOnce("load:" + l, "не загрузился словарь " + l + " (" + err.message + ") — показан ru");
          lang = FALLBACK;
        }
      )
      .then(function () {
        setDocumentLang(lang);
        apply(doc);
        emit();
        return lang;
      });
  }

  function onChange(fn) {
    listeners.push(fn);
    return function off() {
      listeners = listeners.filter(function (x) {
        return x !== fn;
      });
    };
  }

  // Порядок выбора языка: явный параметр → ?lang= в адресе → сохранённый → ru.
  function init(opts) {
    opts = opts || {};
    if (opts.baseUrl) baseUrl = opts.baseUrl;
    if (opts.dicts) {
      SUPPORTED.forEach(function (l) {
        if (opts.dicts[l]) dicts[l] = opts.dicts[l];
      });
    }
    var wanted = normalizeLang(opts.lang) || fromUrl() || readSaved() || FALLBACK;
    // ru нужен всегда — это запасной словарь.
    return loadDict(FALLBACK)
      .catch(function (err) {
        warnOnce("load:ru", "не загрузился основной словарь ru: " + err.message);
        dicts.ru = dicts.ru || {};
      })
      .then(function () {
        if (wanted === FALLBACK) {
          lang = FALLBACK;
          setDocumentLang(lang);
          apply(doc);
          return lang;
        }
        return setLang(wanted);
      });
  }

  // Ключи, которых не хватило за сеанс (для проверки экранов): {kk: [...], ru: [...]}.
  function report() {
    var out = {};
    Object.keys(missing).forEach(function (l) {
      out[l] = Object.keys(missing[l]).sort();
    });
    return out;
  }

  var api = {
    SUPPORTED: SUPPORTED.slice(),
    STORAGE_KEY: STORAGE_KEY,
    init: init,
    ready: null,
    t: t,
    has: has,
    cat: cat,
    setLang: setLang,
    getLang: function () {
      return lang;
    },
    onChange: onChange,
    apply: apply,
    plural: pluralCategory,
    formatNumber: formatNumber,
    formatPercent: formatPercent,
    formatDate: formatDate,
    formatTime: formatTime,
    formatDateTime: formatDateTime,
    formatRelative: formatRelative,
    report: report,
  };

  // Совместимость: модуль R07 (heat.js) ищет переводы в window.Birge.i18n {has(key, lang), t(key, params, lang), lang()}.
  if (root && typeof root === "object" && doc) {
    root.Birge = root.Birge || {};
    if (!root.Birge.i18n) {
      root.Birge.i18n = { t: t, has: has, lang: function () { return lang; }, setLang: setLang, onChange: onChange, ready: null };
    }
  }

  // В браузере словари грузятся сразу; <script data-manual> отключает автозапуск.
  var manual = doc && doc.currentScript && doc.currentScript.hasAttribute("data-manual");
  api.ready = doc && !manual ? init() : Promise.resolve(lang);
  if (root && root.Birge && root.Birge.i18n && root.Birge.i18n.t === t) root.Birge.i18n.ready = api.ready;

  return api;
});
