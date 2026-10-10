/* Birge i18n — переводы ru/kk (R11, раунд 14).
 *
 * Подключение на странице:
 *   <script src="/civic/i18n/messages.js"></script>   (словари; собирается tools/build_i18n.py из ru.json и kk.json)
 *   <script src="/civic/i18n/i18n.js"></script>
 *   <script>Birge.i18n.init().then(start);</script>
 * Без messages.js init() сам загрузит ru.json и kk.json через fetch.
 *
 * Главное API (window.Birge.i18n):
 *   t(key, params)          — строка на текущем языке; {name} в тексте заменяется на params.name;
 *                             если значение — объект форм {one, few, many, other}, форма выбирается по params.count
 *   setLang('kk'|'ru')      — переключить язык без перезагрузки, запомнить выбор, перевести страницу
 *   lang()                  — текущий язык
 *   apply(root)             — перевести элементы с data-i18n / data-i18n-attr внутри root
 *   onChange(fn)            — подписка на смену языка (ещё есть событие window "birge:lang")
 *   bindSwitch(el)          — оживить переключатель ҚАЗ | РУС (кнопки с data-lang внутри el)
 *   formatNumber, formatPercent, formatDate, formatTime, plural — числа и даты по правилам языка
 *   missing()               — список ключей, которых не нашлось (для приёмки R10)
 *
 * Правила:
 *   - нет ключа на казахском → русский текст + console.warn (один раз на ключ);
 *   - нет ключа нигде → возвращается сам ключ (чтобы приёмка его увидела) + console.error;
 *   - даты считаются во времени Астаны (UTC+5) независимо от часового пояса компьютера.
 * Файл работает и в Node (module.exports) — так его проверяют тесты tests/civic/R11/.
 */
(function (root, factory) {
  'use strict';
  var api = factory(root);
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  } else {
    root.Birge = root.Birge || {};
    root.Birge.i18n = api;
  }
})(typeof window !== 'undefined' ? window : globalThis, function (root) {
  'use strict';

  var LANGS = ['ru', 'kk'];
  var FALLBACK = 'ru';
  var STORAGE_KEY = 'birge.lang';
  // Казахстан с 1 марта 2024 живёт в UTC+5 (Астана). Считаем даты сами, а не через часовой пояс
  // компьютера: у владельца, у жюри и на сервере время может быть настроено по-разному.
  var ASTANA_OFFSET_MIN = 5 * 60;
  var NBSP = ' ';

  var MONTHS_SHORT = {
    ru: ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'],
    // В казахском сокращения месяцев читаются плохо — пишем месяц полностью: «11 қазан».
    kk: ['қаңтар', 'ақпан', 'наурыз', 'сәуір', 'мамыр', 'маусым', 'шілде', 'тамыз', 'қыркүйек', 'қазан', 'қараша', 'желтоқсан']
  };
  var MONTHS_LONG = {
    ru: ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'],
    kk: MONTHS_SHORT.kk
  };
  var WEEKDAYS = {
    ru: ['воскресенье', 'понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота'],
    kk: ['жексенбі', 'дүйсенбі', 'сейсенбі', 'сәрсенбі', 'бейсенбі', 'жұма', 'сенбі']
  };

  var messages = { ru: {}, kk: {} };
  var current = FALLBACK;
  var listeners = [];
  var reported = {};      // ключи, о которых уже предупредили в консоли
  var missingKeys = {};   // ключ → языки, где его не нашлось
  var initPromise = null;

  function log(kind, text) {
    if (root.console && typeof root.console[kind] === 'function') root.console[kind]('[i18n] ' + text);
  }

  function storageGet() {
    try { return root.localStorage ? root.localStorage.getItem(STORAGE_KEY) : null; } catch (e) { return null; }
  }
  function storageSet(value) {
    try { if (root.localStorage) root.localStorage.setItem(STORAGE_KEY, value); } catch (e) { /* приватный режим — не страшно */ }
  }

  function normalizeLang(value) {
    var v = String(value || '').toLowerCase();
    if (v.indexOf('kk') === 0 || v.indexOf('kz') === 0) return 'kk';
    if (v.indexOf('ru') === 0) return 'ru';
    return null;
  }

  // Начальный язык: сохранённый выбор → язык браузера → русский.
  function detectLang() {
    var saved = normalizeLang(storageGet());
    if (saved) return saved;
    var nav = root.navigator;
    var list = nav ? (nav.languages || [nav.language]) : [];
    for (var i = 0; i < list.length; i++) {
      if (normalizeLang(list[i]) === 'kk') return 'kk';
    }
    return FALLBACK;
  }

  function addMessages(lang, dict) {
    if (LANGS.indexOf(lang) < 0 || !dict) return;
    var target = messages[lang];
    Object.keys(dict).forEach(function (key) {
      if (key.charAt(0) !== '_') target[key] = dict[key]; // ключи «_meta» — служебные
    });
  }

  // ---------- Склонения ----------
  // Русский: 1 человек / 2 человека / 5 человек / 21 человек / 1,5 человека.
  // Казахский: после числа существительное не меняется («1 адам», «12 адам») — одна форма other.
  function plural(lang, count) {
    var n = Math.abs(Number(count));
    if (!isFinite(n)) return 'other';
    if (lang !== 'ru') return 'other';
    if (Math.floor(n) !== n) return 'other';
    var n10 = n % 10;
    var n100 = n % 100;
    if (n10 === 1 && n100 !== 11) return 'one';
    if (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14)) return 'few';
    return 'many';
  }

  function pickForm(value, lang, params) {
    if (value === null || typeof value !== 'object') return value;
    var count = params && params.count;
    var form = plural(lang, count);
    // Запасные формы: в словаре может не быть нужной — берём ближайшую, но не падаем.
    var order = [form, 'other', 'many', 'few', 'one'];
    for (var i = 0; i < order.length; i++) {
      if (typeof value[order[i]] === 'string') return value[order[i]];
    }
    return null;
  }

  // ---------- Числа ----------
  // «1 666», «4,5», «−3». Группы разрядов — неразрывным пробелом, чтобы число не разрывалось строкой.
  function formatNumber(value, digits) {
    var n = Number(value);
    if (!isFinite(n)) return String(value);
    var d = digits == null ? (Math.round(n) === n ? 0 : 1) : digits;
    var fixed = Math.abs(n).toFixed(d);
    var parts = fixed.split('.');
    var intPart = parts[0];
    if (intPart.length > 3) intPart = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);
    var out = parts.length > 1 && /[1-9]/.test(parts[1]) ? intPart + ',' + parts[1].replace(/0+$/, '') : intPart;
    if (n < 0 && /[1-9]/.test(fixed)) out = '−' + out;
    return out;
  }

  // 0.4 → «40 %» (share=true) или 40 → «40 %».
  function formatPercent(value, share) {
    var n = share ? Number(value) * 100 : Number(value);
    return formatNumber(Math.round(n), 0) + NBSP + '%';
  }

  // ---------- Даты ----------
  // Принимает Date, ISO-строку или «ГГГГ-ММ-ДД». Возвращает части даты во времени Астаны.
  function astanaParts(input) {
    var ms;
    if (input instanceof Date) {
      ms = input.getTime();
    } else if (typeof input === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(input)) {
      // Просто дата без времени — это день по Астане, без сдвигов.
      var p = input.split('-');
      return { y: +p[0], m: +p[1] - 1, d: +p[2], wd: new Date(Date.UTC(+p[0], +p[1] - 1, +p[2])).getUTCDay(), hh: 0, mi: 0 };
    } else {
      ms = new Date(input).getTime();
    }
    if (!isFinite(ms)) return null;
    var t = new Date(ms + ASTANA_OFFSET_MIN * 60000);
    return { y: t.getUTCFullYear(), m: t.getUTCMonth(), d: t.getUTCDate(), wd: t.getUTCDay(), hh: t.getUTCHours(), mi: t.getUTCMinutes() };
  }

  function pad2(n) { return n < 10 ? '0' + n : String(n); }

  // style: 'short' → «11 окт» / «11 қазан»; 'long' → «11 октября 2026» / «2026 жылғы 11 қазан»;
  //        'weekday' → «11 окт, суббота» / «11 қазан, сенбі»; 'datetime' → «11 окт, 10:00».
  function formatDate(input, style, langOverride) {
    var lang = langOverride || current;
    var p = astanaParts(input);
    if (!p) return '';
    var shortDate = p.d + ' ' + MONTHS_SHORT[lang][p.m];
    switch (style) {
      case 'long':
        return lang === 'kk' ? p.y + ' жылғы ' + p.d + ' ' + MONTHS_LONG.kk[p.m] : p.d + ' ' + MONTHS_LONG.ru[p.m] + ' ' + p.y;
      case 'weekday':
        return shortDate + ', ' + WEEKDAYS[lang][p.wd];
      case 'datetime':
        return shortDate + ', ' + pad2(p.hh) + ':' + pad2(p.mi);
      default:
        return shortDate;
    }
  }

  function formatTime(input) {
    var p = astanaParts(input);
    return p ? pad2(p.hh) + ':' + pad2(p.mi) : '';
  }

  // ---------- Перевод ----------
  function noteMissing(key, lang, kind) {
    missingKeys[key] = missingKeys[key] || [];
    if (missingKeys[key].indexOf(lang) < 0) missingKeys[key].push(lang);
    var mark = kind + ':' + lang + ':' + key;
    if (reported[mark]) return;
    reported[mark] = true;
    if (kind === 'fallback') log('warn', 'нет перевода «' + key + '» для ' + lang + ' — показан русский текст');
    else log('error', 'нет ключа «' + key + '» ни в одном словаре');
  }

  function interpolate(text, params, lang) {
    if (!params) return text;
    return text.replace(/\{(\w+)\}/g, function (whole, name) {
      if (!Object.prototype.hasOwnProperty.call(params, name)) return whole;
      var v = params[name];
      if (typeof v === 'number') return formatNumber(v);
      if (v instanceof Date) return formatDate(v, 'short', lang);
      return v == null ? '' : String(v);
    });
  }

  function lookup(lang, key, params) {
    var dict = messages[lang];
    if (!dict || !Object.prototype.hasOwnProperty.call(dict, key)) return null;
    var text = pickForm(dict[key], lang, params);
    return typeof text === 'string' && text !== '' ? text : null;
  }

  function t(key, params, langOverride) {
    var lang = langOverride || current;
    var text = lookup(lang, key, params);
    var used = lang;
    if (text === null && lang !== FALLBACK) {
      text = lookup(FALLBACK, key, params);
      used = FALLBACK;
      if (text !== null) noteMissing(key, lang, 'fallback');
    }
    if (text === null) {
      noteMissing(key, lang, 'absent');
      return key;
    }
    return interpolate(text, params, used);
  }

  function has(key, lang) {
    return lookup(lang || current, key, { count: 1 }) !== null || lookup(lang || current, key, { count: 5 }) !== null;
  }

  // ---------- Страница ----------
  // data-i18n="ключ"                 → textContent
  // data-i18n-attr="placeholder:ключ; aria-label:ключ2"
  // data-i18n-params='{"count": 12}' → параметры для обоих
  function readParams(el) {
    var raw = el.getAttribute('data-i18n-params');
    if (!raw) return undefined;
    try { return JSON.parse(raw); } catch (e) { log('warn', 'неверный JSON в data-i18n-params: ' + raw); return undefined; }
  }

  function apply(rootEl) {
    var doc = root.document;
    var scope = rootEl || doc;
    if (!scope || typeof scope.querySelectorAll !== 'function') return;
    var nodes = scope.querySelectorAll('[data-i18n], [data-i18n-attr]');
    var list = Array.prototype.slice.call(nodes);
    if (scope.getAttribute && (scope.hasAttribute('data-i18n') || scope.hasAttribute('data-i18n-attr'))) list.unshift(scope);
    list.forEach(function (el) {
      var params = readParams(el);
      var key = el.getAttribute('data-i18n');
      if (key) el.textContent = t(key, params);
      var attrs = el.getAttribute('data-i18n-attr');
      if (attrs) {
        attrs.split(';').forEach(function (pair) {
          var idx = pair.indexOf(':');
          if (idx < 0) return;
          var name = pair.slice(0, idx).trim();
          var k = pair.slice(idx + 1).trim();
          if (name && k) el.setAttribute(name, t(k, params));
        });
      }
    });
  }

  function syncSwitches() {
    var doc = root.document;
    if (!doc) return;
    var buttons = doc.querySelectorAll('[data-birge-lang-switch] [data-lang]');
    Array.prototype.forEach.call(buttons, function (b) {
      b.setAttribute('aria-pressed', b.getAttribute('data-lang') === current ? 'true' : 'false');
    });
  }

  function setLang(lang, options) {
    var next = normalizeLang(lang);
    if (!next) { log('warn', 'неизвестный язык «' + lang + '», остаётся ' + current); return current; }
    var changed = next !== current;
    current = next;
    if (!(options && options.persist === false)) storageSet(next);
    var doc = root.document;
    if (doc && doc.documentElement) doc.documentElement.setAttribute('lang', next);
    apply();
    syncSwitches();
    if (changed) {
      listeners.slice().forEach(function (fn) {
        try { fn(next); } catch (e) { log('error', 'обработчик смены языка упал: ' + e.message); }
      });
      if (typeof root.dispatchEvent === 'function' && typeof root.CustomEvent === 'function') {
        root.dispatchEvent(new root.CustomEvent('birge:lang', { detail: { lang: next } }));
      }
    }
    return next;
  }

  function onChange(fn) {
    if (typeof fn !== 'function') return function () {};
    listeners.push(fn);
    return function off() { listeners = listeners.filter(function (x) { return x !== fn; }); };
  }

  // Переключатель: <div class="b-seg" data-birge-lang-switch><button data-lang="kk">ҚАЗ</button><button data-lang="ru">РУС</button></div>
  function bindSwitch(el) {
    if (!el) return;
    el.setAttribute('data-birge-lang-switch', '');
    el.addEventListener('click', function (ev) {
      var btn = ev.target && ev.target.closest ? ev.target.closest('[data-lang]') : null;
      if (btn && el.contains(btn)) setLang(btn.getAttribute('data-lang'));
    });
    syncSwitches();
  }

  function loadJson(url) {
    return root.fetch(url, { cache: 'no-cache' }).then(function (r) {
      if (!r.ok) throw new Error(url + ' → HTTP ' + r.status);
      return r.json();
    });
  }

  // Загружает словари (если их не дал messages.js), ставит язык и переводит страницу.
  // options.base — путь к папке со словарями (по умолчанию /civic/i18n/), options.lang — язык принудительно.
  function init(options) {
    if (initPromise) return initPromise;
    var opts = options || {};
    var base = opts.base || '/civic/i18n/';
    var preset = root.BIRGE_I18N_MESSAGES;
    var load;
    if (preset && preset.ru) {
      addMessages('ru', preset.ru);
      addMessages('kk', preset.kk);
      load = Promise.resolve();
    } else if (typeof root.fetch === 'function') {
      load = Promise.all([loadJson(base + 'ru.json'), loadJson(base + 'kk.json')]).then(function (res) {
        addMessages('ru', res[0]);
        addMessages('kk', res[1]);
      });
    } else {
      load = Promise.reject(new Error('нет словарей и нет fetch'));
    }
    initPromise = load.then(function () {
      setLang(opts.lang || detectLang(), { persist: Boolean(opts.lang) });
      return current;
    }, function (err) {
      // Словари не загрузились — интерфейс не должен остаться пустым: покажем ключи и сообщим в консоль.
      log('error', 'словари не загрузились: ' + err.message);
      current = FALLBACK;
      apply();
      return current;
    });
    return initPromise;
  }

  current = detectLang();

  return {
    LANGS: LANGS.slice(),
    init: init,
    t: t,
    has: has,
    lang: function () { return current; },
    setLang: setLang,
    onChange: onChange,
    apply: apply,
    bindSwitch: bindSwitch,
    addMessages: addMessages,
    plural: plural,
    formatNumber: formatNumber,
    formatPercent: formatPercent,
    formatDate: formatDate,
    formatTime: formatTime,
    missing: function () {
      return Object.keys(missingKeys).map(function (k) { return { key: k, langs: missingKeys[k].slice() }; });
    },
    // Только для тестов: сбросить состояние.
    _reset: function () {
      messages = { ru: {}, kk: {} };
      reported = {};
      missingKeys = {};
      listeners = [];
      initPromise = null;
      current = FALLBACK;
    }
  };
});
