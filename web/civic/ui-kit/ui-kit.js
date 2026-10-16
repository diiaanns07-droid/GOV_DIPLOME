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
 *   BirgeUI.aiTag()                              → <span class="bk-ai"> «ИИ» / «ЖИ» со значком и подсказкой «Подсказка ИИ —
 *                                                  проверьте» (title + скрытый текст для диктора); раунд 15+, поправка П3
 *   BirgeUI.seasonOrder(categories, date?)       → категории в порядке сезона (волна 1, п. 11): с ноября по март
 *                                                  первая «Снег и гололёд», с апреля по октябрь — «Дороги»; остальные
 *                                                  — как в categories_v2.json. Принимает id или объекты с .id; копия.
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

  // Линейная иллюстрация пустого состояния (спрайт ui-kit, символы ill-*)
  function illustration(name) {
    var safe = /^[a-z-]+$/.test(String(name)) ? name : "list";
    return '<svg class="bk-ill" aria-hidden="true" focusable="false"><use href="' + SPRITE + "#ill-" + safe + '"></use></svg>';
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
    // Чистый дизайн (CLEAN_PASS, правило 10): на экране один тост — новый заменяет прежние. Исключение — ошибка
    // с «Повторить»: её не убирает обычное сообщение (иначе человек не успеет повторить), только новая ошибка.
    var box = toastContainer();
    Array.prototype.slice.call(box.children).forEach(function (old) {
      if (old.__bkClose && !(old.__bkSticky && !isError)) old.__bkClose();
    });
    el.__bkClose = close;
    el.__bkSticky = !!(isError && opts.action);
    box.appendChild(el);
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
  // opts.text — «ҚАЗ · РУС» текстом (чистый дизайн, шапка в одну строку), иначе сегмент с подложкой.
  function langSwitch(el, opts) {
    var I = root.BirgeI18n;
    el.classList.add(opts && opts.text ? "bk-langtext" : "bk-seg");
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
    // Иллюстрация из линий (дизайн-марафон): по умолчанию «список» для пустого и «нет связи» для ошибки;
    // opts.illustration — list | map | search | done | offline | idea | question | staff (вход сотрудника); opts.icon — прежняя иконка 48 px.
    var art = opts.icon ? icon(opts.icon, { size: 48 })
      : illustration(opts.illustration || (isError ? "offline" : "list"));
    el.innerHTML =
      '<div class="' + (isError ? "bk-error" : "bk-empty") + '" role="' + (isError ? "alert" : "status") + '">' +
      art +
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

  // Статус-иконка (правило 3 Linear): тот же рисунок, что у .bk-status, для карты, строк и своих разметок.
  // statusIcon("in_progress", 14) → '<svg class="bk-st-ic" data-status="in_progress" …><use href="…#st-half"/></svg>'
  var STATUS_SHAPE = { new: "st-ring", reopened: "st-ring", accepted: "st-ring", in_progress: "st-half",
    reported_fixed: "st-ring-check", fixed: "st-ring-check", verified: "st-done", rejected: "st-reject" };
  function statusIcon(status, size) {
    var px = Math.min(64, Math.max(8, Math.round(Number(size)) || 14)), shape = STATUS_SHAPE[status] || "st-ring";  // R15-S41: только число
    return '<svg class="bk-st-ic" data-status="' + esc(status || "new") + '" width="' + px + '" height="' + px +
      '" aria-hidden="true" focusable="false"><use href="' + SPRITE + "#" + shape + '"/></svg>';
  }

  // Скелетон списка «как в Linear» (правило 4: не дольше 150 мс): skelRows(3) → 3 строки .bk-lrow--skel той же высоты 44
  function skelRows(n) {
    var html = "", w = [62, 48, 70, 55, 66];
    for (var i = 0; i < (n || 3); i++) {
      html += '<div class="bk-lrow bk-lrow--skel" aria-hidden="true"><span class="bk-skel" style="width:14px;height:14px;margin:0 7px;border-radius:50%"></span>' +
        '<span class="bk-skel" style="width:' + w[i % w.length] + '%"></span><span class="bk-skel" style="width:28px;margin-left:auto"></span></div>';
    }
    return html;
  }

  // Одно состояние «войдите как сотрудник» для всех разделов (марафон, INTEGRATION §9.3 b): линейная иллюстрация staff,
  // заголовок, подсказка «Учётную запись выдаёт администратор.» и одна главная кнопка «Войти». loginState(el, onLogin, opts)
  // opts: title / text / label — свои тексты (например, ask.staff.login у «Вопроса акиму»).
  function loginState(el, onLogin, opts) {
    opts = opts || {};
    state(el, "empty", {
      illustration: "staff",
      title: opts.title || tr("proposal.need_staff"),
      text: opts.text != null ? opts.text : tr("staff.login.note"),
      action: { label: opts.label || tr("staff.login.submit"), onClick: onLogin },
    });
  }

  // Меню аватара (чистый дизайн): кнопка .bk-avatar открывает список .bk-menu под собой у правого края.
  // Esc, щелчок мимо и выбор пункта закрывают; ↑/↓ — по пунктам. menu(button, list) → {open(), close()}.
  function menu(button, list) {
    function items() { return Array.prototype.slice.call(list.querySelectorAll(".bk-menu__item")); }
    function place() {
      var b = button.getBoundingClientRect();
      list.style.top = Math.round(b.bottom + 8 + root.scrollY) + "px";
      list.style.right = Math.max(8, Math.round(doc.documentElement.clientWidth - b.right)) + "px";
    }
    function open() {
      list.hidden = false;
      place();
      button.setAttribute("aria-expanded", "true");
      var first = items()[0];
      if (first) first.focus();
    }
    function close(focusBack) {
      if (list.hidden) return;
      list.hidden = true;
      button.setAttribute("aria-expanded", "false");
      if (focusBack) button.focus();
    }
    button.setAttribute("aria-haspopup", "menu");
    button.setAttribute("aria-expanded", "false");
    list.setAttribute("role", "menu");
    list.hidden = true;
    button.addEventListener("click", function () { if (list.hidden) open(); else close(false); });
    list.addEventListener("click", function (e) { if (e.target.closest(".bk-menu__item")) close(true); });
    doc.addEventListener("click", function (e) { if (!list.contains(e.target) && !button.contains(e.target)) close(false); });
    doc.addEventListener("keydown", function (e) {
      if (list.hidden) return;
      if (e.key === "Escape") { e.preventDefault(); close(true); return; }
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      var all = items(), i = all.indexOf(doc.activeElement);
      e.preventDefault();
      all[(i + (e.key === "ArrowDown" ? 1 : all.length - 1) + all.length) % all.length].focus();
    });
    return { open: open, close: close };
  }

  // Вкладки раздела (волна 2): <div class="bk-tabs" role="tablist"><button role="tab" value="…">…</button></div>.
  // Отмечает выбранную (aria-selected, tabindex), стрелки ←/→ переходят между вкладками; onChange(value) — по выбору.
  function tabs(el, onChange) {
    function all() { return Array.prototype.slice.call(el.querySelectorAll('[role="tab"]')); }
    function select(btn, focus) {
      all().forEach(function (b) {
        b.setAttribute("aria-selected", b === btn ? "true" : "false");
        b.tabIndex = b === btn ? 0 : -1;
      });
      if (focus) btn.focus();
      if (btn.scrollIntoView) btn.scrollIntoView({ block: "nearest", inline: "nearest" });
      if (onChange) onChange(btn.value || btn.getAttribute("data-value"));
    }
    el.addEventListener("click", function (e) {
      var b = e.target.closest ? e.target.closest('[role="tab"]') : null;
      if (b && el.contains(b)) select(b, false);
    });
    el.addEventListener("keydown", function (e) {
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      var list = all(), i = list.indexOf(doc.activeElement);
      if (i < 0) return;
      e.preventDefault();
      select(list[(i + (e.key === "ArrowRight" ? 1 : list.length - 1)) % list.length], true);
    });
    var cur = el.querySelector('[role="tab"][aria-selected="true"]') || all()[0];
    all().forEach(function (b) {
      b.setAttribute("aria-selected", b === cur ? "true" : "false");
      b.tabIndex = b === cur ? 0 : -1;
    });
    // Не помещаются (длинные kk-подписи на 375) — край строки затухает, пока есть что прокрутить вправо.
    scrollFade(el);
  }

  // Ряд, который прокручивается вбок (вкладки, фильтры-чипы «Обращений», чипы уточнений): data-more="true", пока справа
  // есть что прокрутить — CSS ui-kit даёт мягкое затухание края (.bk-tabs, .bk-scroll-x). scrollFade(el) → el.
  function scrollFade(el) {
    if (el.__bkFade) return el; // уже подключено (вкладки ui-kit или автоподключение ниже)
    el.__bkFade = true;
    function edge() {
      var more = el.scrollWidth - el.clientWidth - el.scrollLeft > 2;
      if (more) el.setAttribute("data-more", "true");
      else el.removeAttribute("data-more");
    }
    el.addEventListener("scroll", edge, { passive: true });
    if (typeof ResizeObserver !== "undefined") new ResizeObserver(edge).observe(el);
    edge();
    return el;
  }

  // Сезонный порядок категорий (POLISH_WAVE п. 11). Месяц — по часам устройства: зимой житель не ищет снег в конце.
  function seasonOrder(categories, date) {
    var list = (categories || []).slice();
    var month = (date || new Date()).getMonth() + 1;
    var first = month >= 11 || month <= 3 ? "snow_ice" : "roads";
    var idOf = function (c) { return c && typeof c === "object" ? c.id : c; };
    for (var i = 0; i < list.length; i++) {
      if (idOf(list[i]) === first) { list.unshift(list.splice(i, 1)[0]); break; }
    }
    return list;
  }

  // Автоподключение затухания края: роли размечают .bk-tabs / .bk-scroll-x и не всегда вызывают BirgeUI.tabs — на телефоне
  // казахские вкладки обрезались краем без признака прокрутки (R10 DESIGN_REVIEW, круг 2: «Рядом», «Идеи»).
  // Новые узлы ловит MutationObserver; повторно один и тот же ряд не подключается.
  function autoFade(node) {
    if (!node || node.nodeType !== 1) return;
    if (node.matches && node.matches(".bk-tabs, .bk-scroll-x")) scrollFade(node);
    if (node.querySelectorAll) Array.prototype.forEach.call(node.querySelectorAll(".bk-tabs, .bk-scroll-x"), scrollFade);
  }
  if (doc && typeof MutationObserver !== "undefined") {
    var startFade = function () {
      autoFade(doc.body);
      new MutationObserver(function (list) {
        list.forEach(function (m) { Array.prototype.forEach.call(m.addedNodes, autoFade); });
      }).observe(doc.body, { childList: true, subtree: true });
    };
    if (doc.readyState === "loading") doc.addEventListener("DOMContentLoaded", startFade);
    else if (doc.body) startFade();
  }

  // Метка «ИИ» (П3): у подсказки модели — значок набора и слово, без свечения (П1). Тексты — словарь на момент вызова
  // (модули перерисовывают экран при смене языка); подсказка — title для мыши и скрытый текст для диктора.
  function aiTag() {
    var hint = tr("common.ai.hint");
    var el = doc.createElement("span");
    el.className = "bk-ai";
    el.title = hint;
    el.innerHTML = icon("ai") + '<span class="bk-ai__t" aria-hidden="true">' + esc(tr("common.ai.badge")) + "</span>" +
      '<span class="bk-sr-only">' + esc(hint) + "</span>";
    return el;
  }

  root.BirgeUI = { icon: icon, toast: toast, sheet: sheet, seg: seg, langSwitch: langSwitch, state: state, statusIcon: statusIcon, skelRows: skelRows, loginState: loginState, scrollFade: scrollFade, esc: esc,
    seasonOrder: seasonOrder, tabs: tabs, menu: menu, illustration: illustration, aiTag: aiTag, SPRITE: SPRITE };
})(typeof self !== "undefined" ? self : this);
