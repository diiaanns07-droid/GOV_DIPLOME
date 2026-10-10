/*
 * Birge · ui-kit · помощники (R11, раунд 14). Без библиотек.
 * Нужен для одинакового поведения во всех модулях: иконки, тосты, шторка, ҚАЗ/РУС, состояния блока.
 *
 *   BirgeUI.icon("bus")                          → строка <svg class="ic">…</svg> (aria-hidden)
 *   BirgeUI.toast("Сохранено")                   → тост на 4 с
 *   BirgeUI.toast(text, {type:"error", action:{label, onClick}})  → ошибка с кнопкой «Повторить»
 *   BirgeUI.sheet(el)                            → шторка: тап по ручке и перетаскивание peek/half/full
 *   BirgeUI.seg(el, onChange)                    → сегментный переключатель (aria-pressed)
 *   BirgeUI.langSwitch(el)                       → ҚАЗ | РУС, связан с BirgeI18n
 *   BirgeUI.state(el, "loading"|"empty"|"error", {title, text, action:{label,onClick}})
 *
 * Тексты берутся из BirgeI18n, если он подключён; сам ui-kit.js слов не содержит.
 */
(function (root) {
  "use strict";
  var doc = root.document;
  var base = "";
  if (doc && doc.currentScript && doc.currentScript.src) base = doc.currentScript.src.replace(/[^/]*$/, "");
  var SPRITE = base + "icons.svg";

  function tr(key, params) {
    return root.BirgeI18n ? root.BirgeI18n.t(key, params) : key;
  }

  // Подписи ставим только после загрузки словарей и обновляем при смене языка.
  function whenText(fn) {
    var I = root.BirgeI18n;
    if (!I) return fn();
    I.ready.then(fn);
    I.onChange(fn);
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // Иконка из спрайта. Подпись рядом с иконкой — забота вызывающего (UX_BRIEF, правило 3).
  function icon(name, opts) {
    var size = opts && parseInt(opts.size, 10); // только число: строка из вызова не попадёт в разметку
    var cls = "ic" + (size ? " ic--" + size : "");
    return (
      '<svg class="' + cls + '" aria-hidden="true" focusable="false"><use href="' + SPRITE + "#i-" + esc(name) + '"></use></svg>'
    );
  }

  // ── Тосты ──
  var toastBox = null;
  function toastContainer() {
    if (toastBox && doc.body.contains(toastBox)) return toastBox;
    toastBox = doc.createElement("div");
    toastBox.className = "bk-toasts";
    doc.body.appendChild(toastBox);
    return toastBox;
  }

  function toast(text, opts) {
    opts = opts || {};
    var el = doc.createElement("div");
    var isError = opts.type === "error";
    el.className = "bk-toast" + (opts.type ? " bk-toast--" + opts.type : "");
    // Ошибка зачитывается сразу (alert), обычное сообщение — вежливо (status).
    el.setAttribute("role", isError ? "alert" : "status");
    var iconName = isError ? "wifi-off" : opts.type === "ok" ? "check" : null;
    el.innerHTML = (iconName ? icon(iconName) : "") + '<span class="bk-toast__text"></span>';
    el.querySelector(".bk-toast__text").textContent = text;
    var timer = null;
    function close() {
      clearTimeout(timer);
      if (el.parentNode) el.parentNode.removeChild(el);
    }
    if (opts.action) {
      var b = doc.createElement("button");
      b.type = "button";
      b.className = "bk-btn";
      b.textContent = opts.action.label || tr("common.action.retry");
      b.addEventListener("click", function () {
        close();
        if (opts.action.onClick) opts.action.onClick();
      });
      el.appendChild(b);
    }
    var x = doc.createElement("button");
    x.type = "button";
    x.className = "bk-iconbtn";
    x.style.color = "inherit";
    x.setAttribute("aria-label", tr("common.action.close"));
    x.innerHTML = icon("close");
    x.addEventListener("click", close);
    el.appendChild(x);
    toastContainer().appendChild(el);
    // Ошибка с действием висит, пока её не закроют: пользователь должен успеть нажать «Повторить».
    var ms = opts.timeout != null ? opts.timeout : isError && opts.action ? 0 : 4000;
    if (ms > 0) timer = setTimeout(close, ms);
    return { close: close, el: el };
  }

  // ── Шторка ──
  var SNAPS = ["peek", "half", "full"];
  function sheet(el, opts) {
    opts = opts || {};
    var handle = el.querySelector(".bk-sheet__handle");
    if (!el.dataset.snap) el.dataset.snap = "peek";
    // Высота области, в которой живёт шторка: окно (fixed) или рамка-родитель (absolute, как в витрине).
    function areaHeight() {
      return getComputedStyle(el).position === "absolute" && el.offsetParent ? el.offsetParent.clientHeight : root.innerHeight;
    }
    // Значение CSS-переменной в пикселях: поддерживает px и vh.
    function cssLen(name, fallback) {
      var v = getComputedStyle(el).getPropertyValue(name).trim();
      var n = parseFloat(v);
      if (!isFinite(n)) return fallback;
      return /vh$/.test(v) ? (n * root.innerHeight) / 100 : n;
    }
    function set(snap) {
      el.dataset.snap = snap;
      if (handle) handle.setAttribute("aria-expanded", snap === "peek" ? "false" : "true");
      if (opts.onChange) opts.onChange(snap);
    }
    if (handle) {
      whenText(function () {
        handle.setAttribute("aria-label", tr("common.sheet.toggle"));
      });
      // Тап по ручке: peek → half → full → peek
      handle.addEventListener("click", function () {
        if (moved) return;
        set(SNAPS[(SNAPS.indexOf(el.dataset.snap) + 1) % SNAPS.length]);
      });
      // Перетаскивание: шторка идёт за пальцем, при отпускании прилипает к ближайшему положению.
      var startY = 0;
      var startH = 0;
      var moved = false;
      var dragging = false;
      handle.addEventListener("pointerdown", function (e) {
        dragging = true;
        moved = false;
        startY = e.clientY;
        startH = el.getBoundingClientRect().height;
        handle.setPointerCapture(e.pointerId);
        el.style.transition = "none";
      });
      handle.addEventListener("pointermove", function (e) {
        if (!dragging) return;
        var dy = e.clientY - startY;
        if (Math.abs(dy) > 4) moved = true;
        // шторка идёт за пальцем: высота = исходная − сдвиг, в пределах [peek, full]
        var h = Math.max(cssLen("--sheet-peek", 120), Math.min(cssLen("--sheet-full", areaHeight() * 0.92), startH - dy));
        el.style.height = h + "px";
      });
      function end() {
        if (!dragging) return;
        dragging = false;
        var h = el.getBoundingClientRect().height; // видимая высота шторки
        el.style.transition = "";
        el.style.height = "";
        if (!moved) return;
        var area = areaHeight();
        var targets = { peek: cssLen("--sheet-peek", 120), half: cssLen("--sheet-half", area * 0.5), full: cssLen("--sheet-full", area * 0.92) };
        var best = "peek";
        SNAPS.forEach(function (s) {
          if (Math.abs(targets[s] - h) < Math.abs(targets[best] - h)) best = s;
        });
        set(best);
        setTimeout(function () {
          moved = false;
        }, 0);
      }
      handle.addEventListener("pointerup", end);
      handle.addEventListener("pointercancel", end);
    }
    return { set: set, get: function () { return el.dataset.snap; } };
  }

  // ── Сегментный переключатель ──
  function seg(el, onChange) {
    el.addEventListener("click", function (e) {
      var b = e.target.closest("button");
      if (!b || !el.contains(b)) return;
      Array.prototype.forEach.call(el.querySelectorAll("button"), function (x) {
        x.setAttribute("aria-pressed", x === b ? "true" : "false");
      });
      if (onChange) onChange(b.value || b.dataset.value);
    });
  }

  // ── ҚАЗ | РУС ──
  function langSwitch(el) {
    var I = root.BirgeI18n;
    el.classList.add("bk-seg");
    el.setAttribute("role", "group");
    el.innerHTML =
      '<button type="button" value="kk" lang="kk">ҚАЗ</button><button type="button" value="ru" lang="ru">РУС</button>';
    function sync() {
      var cur = I ? I.getLang() : "ru";
      el.setAttribute("aria-label", tr("common.lang.label"));
      Array.prototype.forEach.call(el.querySelectorAll("button"), function (b) {
        b.setAttribute("aria-pressed", b.value === cur ? "true" : "false");
      });
    }
    seg(el, function (value) {
      if (I) I.setLang(value);
    });
    whenText(sync);
  }

  // ── Состояния блока: загрузка / пусто / ошибка ──
  function state(el, kind, opts) {
    opts = opts || {};
    el.setAttribute("aria-busy", kind === "loading" ? "true" : "false");
    if (kind === "loading") {
      el.innerHTML =
        '<div class="bk-card" aria-hidden="true"><span class="bk-skel bk-skel--title"></span>' +
        '<span class="bk-skel bk-skel--line"></span><span class="bk-skel bk-skel--line" style="width:60%"></span></div>' +
        '<p class="bk-meta" role="status"></p>';
      el.querySelector("[role=status]").textContent = opts.text || tr("common.state.loading");
      return;
    }
    var isError = kind === "error";
    el.innerHTML =
      '<div class="' + (isError ? "bk-error" : "bk-empty") + '" role="' + (isError ? "alert" : "status") + '">' +
      icon(opts.icon || (isError ? "wifi-off" : "search"), { size: 48 }) +
      '<p class="' + (isError ? "bk-error__title" : "bk-empty__title") + '"></p>' +
      '<p class="' + (isError ? "bk-error__text" : "bk-empty__text") + '"></p></div>';
    var box = el.firstChild;
    box.children[1].textContent = opts.title || tr(isError ? "common.state.network_title" : "common.state.empty_title");
    var text = opts.text != null ? opts.text : isError ? tr("common.state.network_text") : "";
    if (text) box.children[2].textContent = text;
    else box.removeChild(box.children[2]);
    if (opts.action || isError) {
      var b = doc.createElement("button");
      b.type = "button";
      b.className = "bk-btn" + (isError ? "" : " bk-btn--primary");
      var a = opts.action || {};
      b.innerHTML = isError ? icon("refresh") : "";
      b.appendChild(doc.createTextNode(a.label || tr("common.action.retry")));
      if (a.onClick) b.addEventListener("click", a.onClick);
      box.appendChild(b);
    }
  }

  root.BirgeUI = { icon: icon, toast: toast, sheet: sheet, seg: seg, langSwitch: langSwitch, state: state, esc: esc, SPRITE: SPRITE };
})(typeof self !== "undefined" ? self : this);
