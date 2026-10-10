/*
 * R06 · карточки «Предложение» и «Этапы объекта» (раунд 14). Без библиотек.
 *
 * Нужны (подключить раньше): /civic/ui-kit/tokens.css, components.css, ui-kit.js (BirgeUI),
 * /civic/i18n/i18n.js (BirgeI18n). Свои стили — /civic/proposals/proposals.css.
 *
 *   BirgeProposals.mountProposal(el, id, {role:"resident"|"akimat"})   загрузить и показать предложение
 *   BirgeProposals.renderProposal(el, proposal, opts)                  показать уже загруженное
 *   BirgeProposals.mountObject(el, id)                                  объект: полоса 6 этапов + отставание
 *   BirgeProposals.renderStages(el, object)                             только блок этапов (для чужих карточек)
 *   BirgeProposals.api                                                  запросы к /api/civic/v2 (CONTRACT §7)
 *   BirgeProposals.deviceId()                                           случайный id устройства (localStorage)
 *
 * Голос: «За» / «Против», один голос с устройства. Повторное нажатие той же кнопки ничего не
 * добавляет, другой — меняет голос. Счётчики всегда берутся из ответа сервера, а не считаются здесь.
 */
(function (root) {
  "use strict";

  var API = "/api/civic/v2";
  var DEVICE_KEY = "birge.device_id";
  var STAGES = ["planned", "design", "procurement", "construction", "acceptance", "operating"];
  var KIND_ICON = { square: "trees", playground: "playground", sports: "ball", stop: "bus", lighting: "bulb" };
  var OBJECT_ICON = { construction: "building", roadworks: "road", landscaping: "trees", event: "calendar" };
  // Статус предложения → цвет значка ui-kit (слово рядом всегда своё).
  var STATUS_LOOK = { proposal: "accepted", approved: "fixed", rejected: "rejected" };

  // Все тексты — из словарей R11 (web/civic/i18n, ветка claude/r14-R11): 33 ключа R06 там с 12 октября.
  // Запасной список PENDING убран (STATUS R06, «следующий шаг»): нет ключа — i18n покажет ключ и предупредит.

  function I() {
    return root.BirgeI18n;
  }
  function lang() {
    return I() ? I().getLang() : "ru";
  }
  function t(key, params) {
    var i18n = I();
    return i18n ? i18n.t(key, params) : key;
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function icon(name) {
    return root.BirgeUI ? root.BirgeUI.icon(name) : "";
  }
  function date(iso) {
    return I() && iso ? I().formatDate(iso) : iso || "";
  }
  function toast(text, opts) {
    if (root.BirgeUI) root.BirgeUI.toast(text, opts);
  }

  // ── Устройство ──
  var memoryDevice = null;
  function randomId() {
    var bytes = new Uint8Array(16);
    if (root.crypto && root.crypto.getRandomValues) root.crypto.getRandomValues(bytes);
    else for (var i = 0; i < bytes.length; i++) bytes[i] = Math.floor(Math.random() * 256);
    return "dev-" + Array.prototype.map.call(bytes, function (b) { return ("0" + b.toString(16)).slice(-2); }).join("");
  }
  // Случайная строка, не связанная с человеком. Сервер хранит только её хэш с солью.
  function deviceId() {
    try {
      var saved = root.localStorage.getItem(DEVICE_KEY);
      if (saved && /^[A-Za-z0-9_-]{16,128}$/.test(saved)) return saved;
      var fresh = randomId();
      root.localStorage.setItem(DEVICE_KEY, fresh);
      return fresh;
    } catch (e) {
      // Приватный режим: голос учтётся до закрытия вкладки.
      return memoryDevice || (memoryDevice = randomId());
    }
  }

  // ── API ──
  function request(method, path, body, headers) {
    var opts = { method: method, credentials: "same-origin", headers: { Accept: "application/json" } };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    Object.keys(headers || {}).forEach(function (k) { opts.headers[k] = headers[k]; });
    return root.fetch(path, opts).then(
      function (res) {
        return res.json().then(
          function (json) {
            return unwrap(res, json);
          },
          function () {
            var err = new Error("HTTP " + res.status);
            err.status = res.status;
            err.code = res.status === 404 ? "not_found" : "bad_response";
            throw err;
          }
        );
      },
      function (netErr) {
        var err = new Error("network");
        err.status = 0;
        err.code = "network";
        throw err;
      }
    );
  }
  // Два формата ответа: конверт R02/R06 {ok, data | error:{code, message}} и «голый» JSON шлюза R01
  // (успех — сам объект, ошибка — {error: "код", message}). Карточкам всё равно, через что их подключили.
  function unwrap(res, json) {
    if (res.ok && json && json.ok === true) return json.data;
    if (res.ok && json && json.ok === undefined && !json.error) return json;
    var e = (json && json.error) || {};
    var err = new Error((typeof e === "object" ? e.message : json && json.message) || "HTTP " + res.status);
    err.status = res.status;
    err.code = typeof e === "string" ? e : e.code;
    err.fields = (typeof e === "object" && e.fields) || (json && json.fields) || {};
    return Promise.reject(err);
  }
  var csrfToken = null;
  function csrf() {
    if (csrfToken) return Promise.resolve(csrfToken);
    return request("GET", "/api/civic/v1/session").then(function (data) {
      if (!data.authenticated) {
        var err = new Error("unauthenticated");
        err.status = 401;
        err.code = "unauthenticated";
        throw err;
      }
      return (csrfToken = data.csrf_token);
    });
  }
  var api = {
    proposal: function (id) {
      return request("GET", API + "/proposals/" + encodeURIComponent(id) + "?device_id=" + encodeURIComponent(deviceId()));
    },
    proposals: function (query) {
      var q = "device_id=" + encodeURIComponent(deviceId()) + (query ? "&" + query : "");
      return request("GET", API + "/proposals?" + q);
    },
    vote: function (id, value) {
      return request("POST", API + "/proposals/" + encodeURIComponent(id) + "/vote", { value: value, device_id: deviceId() });
    },
    decide: function (id, action, reason) {
      return csrf().then(function (token) {
        return request("POST", API + "/proposals/" + encodeURIComponent(id) + "/" + action, reason ? { reason: reason } : {}, {
          "X-CSRF-Token": token,
        });
      });
    },
    object: function (id) {
      return request("GET", API + "/objects/" + encodeURIComponent(id));
    },
    objects: function (query) {
      return request("GET", API + "/objects" + (query ? "?" + query : ""));
    },
    lagging: function (district) {
      return request("GET", API + "/objects/lagging" + (district ? "?district=" + encodeURIComponent(district) : ""));
    },
  };

  // Служебные слова в названии демо-записи («Демо: …», «… (синтетика)») не показываем: метка «Пример» уже стоит
  // (UX_REVIEW R11 день 3 п. 15; то же делает «Картина дня» R08). Только для demo: true.
  function demoTitle(text) {
    var clean = String(text || "")
      .replace(/^\s*(Демо|Demo|Үлгі)\s*[:·—-]\s*/i, "")
      .replace(/\s*\((синтетика|synthetic|демо|demo)\)\s*$/i, "")
      .trim();
    return clean ? clean.charAt(0).toUpperCase() + clean.slice(1) : text;
  }

  // ── Предложение ──
  function title(p) {
    // Казахское название, если акимат его ввёл; иначе русское с lang="ru" (экранный диктор прочтёт верно).
    if (lang() === "kk" && p.title_kk) return { text: p.title_kk, lang: "kk" };
    return { text: p.title_ru, lang: "ru" };
  }

  function proposalHtml(p, opts) {
    var akimat = opts.role === "akimat";
    var id = "r06-p-" + esc(p.id);
    var ttl = title(p);
    var total = p.votes_up + p.votes_down;
    var upShare = total ? Math.round((p.votes_up / total) * 100) : 0;
    var tags =
      '<span class="bk-tag bk-tag--project">' + esc(p.planned_year ? t("proposal.label", { year: String(p.planned_year) }) : t("common.tag.project")) + "</span>" +
      (p.demo ? '<span class="bk-tag bk-tag--demo" title="' + esc(t("common.tag.demo_hint")) + '">' + esc(t("common.tag.demo")) + "</span>" : "");
    var voteBtn = function (value, key, ic, count) {
      var pressed = p.my_vote === value;
      return (
        '<button class="bk-btn r06-vote__btn" type="button" data-value="' + value + '" aria-pressed="' + pressed + '"' +
        (p.voting_open ? "" : " disabled") + '><span class="r06-vote__label">' + icon(ic) + "<span>" + esc(t(key)) + '</span></span><span class="bk-btn__count">' +
        esc(I() ? I().formatNumber(count) : count) + "</span></button>"
      );
    };
    var note = p.my_vote === 1 ? t("proposal.your_vote_up") : p.my_vote === -1 ? t("proposal.your_vote_down") : t("proposal.one_vote");
    if (!p.voting_open) note = t("proposal.voting_closed");
    var html =
      '<article class="bk-card r06-card" aria-labelledby="' + id + '" data-proposal="' + esc(p.id) + '">' +
      '<div class="bk-card__row"><span class="bk-card__eyebrow">' + icon(KIND_ICON[p.kind] || "flag") + "<span>" +
      esc(t("proposal.kind." + p.kind)) + "</span></span>" + tags + "</div>" +
      '<h3 class="bk-card__title" id="' + id + '" lang="' + ttl.lang + '">' + esc(ttl.text) + "</h3>" +
      (p.district ? '<p class="bk-meta" style="margin:0">' + esc(t("district.name", { name: t("district." + p.district) })) + "</p>" : "") +
      '<div class="bk-card__row"><span class="bk-meta">' + esc(t("status.label")) + '</span><span class="bk-status" data-status="' +
      (STATUS_LOOK[p.status] || "new") + '">' + esc(t("proposal.status." + p.status)) + "</span></div>" +
      (akimat
        ? // Акимат голосует не здесь: голоса — числами (только чтение), одна главная кнопка — «Одобрить»
          // (UX_REVIEW R11, день 3, п. 16). Текст — тот же, что в «Картине дня» R08 (akim.proposals.votes).
          '<p class="r06-tally">' + icon("users") + "<span>" + esc(t("akim.proposals.votes", { up: p.votes_up, down: p.votes_down })) + "</span></p>"
        : '<div class="r06-vote" role="group" aria-label="' + esc(t("proposal.votes_aria", { up: p.votes_up, down: p.votes_down })) + '">' +
          voteBtn(1, "proposal.vote_up", "thumb-up", p.votes_up) + voteBtn(-1, "proposal.vote_down", "thumb-down", p.votes_down) + "</div>") +
      '<div class="r06-share" aria-hidden="true"><i class="r06-share__up" style="width:' + upShare + '%"></i><i class="r06-share__down" style="width:' +
      (total ? 100 - upShare : 0) + '%"></i></div>' +
      (akimat ? (p.voting_open ? "" : '<p class="bk-meta r06-vote__note">' + esc(t("proposal.voting_closed")) + "</p>")
        : '<p class="bk-meta r06-vote__note" aria-live="polite">' + esc(note) + "</p>");
    if (akimat && p.status === "proposal") {
      html +=
        '<div class="bk-actions"><button class="bk-btn bk-btn--primary" type="button" data-action="approve">' + icon("check") +
        "<span>" + esc(t("proposal.approve")) + '</span></button><button class="bk-btn bk-btn--danger" type="button" data-action="reject">' +
        icon("close") + "<span>" + esc(t("proposal.reject")) + "</span></button></div>";
    }
    return html + "</article>";
  }

  function renderProposal(el, proposal, opts) {
    opts = opts || {};
    var state = { p: proposal, busy: false };
    function draw() {
      el.innerHTML = proposalHtml(state.p, opts);
    }
    function failed(err, retry) {
      if (err.status === 429) {
        // Лимит голосов с адреса (R15 S08): «Повторить» тут не поможет — без кнопки, понятными словами.
        toast(known("proposal.vote_limit"), { type: "error" });
        return;
      }
      var key = err.code === "voting_closed" ? "proposal.voting_closed"
        : err.code === "already_decided" ? "proposal.already_decided"
        : err.status === 401 || err.code === "csrf_failed" ? "proposal.need_staff"
        : err.status === 404 ? "proposal.not_found" : "proposal.vote_error";
      if (err.code === "voting_closed" || err.code === "already_decided") {
        return api.proposal(state.p.id).then(function (d) { state.p = d.item; draw(); toast(t(key)); }, function () { toast(t(key)); });
      }
      toast(t(key), key === "proposal.vote_error" ? { type: "error", action: { label: t("common.action.retry"), onClick: retry } } : { type: "error" });
    }
    function vote(value) {
      if (state.busy || !state.p.voting_open) return;
      state.busy = true;
      var btn = el.querySelector('.r06-vote__btn[data-value="' + value + '"]');
      if (btn) btn.setAttribute("aria-busy", "true");
      api.vote(state.p.id, value).then(
        function (data) {
          state.busy = false;
          state.p = data.item;
          draw();
          toast(t(data.changed && data.previous ? "proposal.vote_changed" : "proposal.vote_saved"));
          var again = el.querySelector('.r06-vote__btn[data-value="' + value + '"]');
          if (again) again.focus(); // фокус остаётся на нажатой кнопке после перерисовки
          if (opts.onChange) opts.onChange(state.p);
        },
        function (err) {
          state.busy = false;
          if (btn) btn.removeAttribute("aria-busy");
          failed(err, function () { vote(value); });
        }
      );
    }
    function decide(action, btn) {
      if (state.busy) return;
      state.busy = true;
      btn.setAttribute("aria-busy", "true");
      btn.disabled = true;
      api.decide(state.p.id, action).then(
        function (data) {
          state.busy = false;
          state.p = data.item;
          draw();
          toast(t("proposal.status." + state.p.status));
          if (opts.onChange) opts.onChange(state.p);
        },
        function (err) {
          state.busy = false;
          btn.disabled = false;
          btn.removeAttribute("aria-busy");
          failed(err, function () { decide(action, btn); });
        }
      );
    }
    el.onclick = function (e) {
      var b = e.target.closest && e.target.closest("button");
      if (!b || !el.contains(b) || b.disabled) return;
      if (b.hasAttribute("data-value")) vote(Number(b.getAttribute("data-value")));
      else if (b.hasAttribute("data-action")) decide(b.getAttribute("data-action"), b);
    };
    draw();
    if (I()) I().onChange(draw);
    return { get: function () { return state.p; }, redraw: draw };
  }

  // Новый ключ (ночь 10→11 окт), передан R11 в INTEGRATION §5: пока его нет в словаре — текст отсюда, без
  // предупреждений; как только ключ есть в ru.json/kk.json — побеждает словарь.
  var NEW_KEYS = {
    "proposal.vote_limit": {
      // Текст — как в словаре R11 (KK_REVIEW): «адрес» житель поймёт как домашний, лимит же — по сети.
      ru: "С этого устройства или сети уже много голосов за этот проект. Попробуйте завтра.",
      kk: "Бұл құрылғыдан немесе желіден осы жобаға дауыс көп берілді. Ертең қайталап көріңіз.",
    },
  };
  function known(key, params) {
    var i18n = I();
    if (i18n && i18n.has && i18n.has(key)) return i18n.t(key, params);
    var p = NEW_KEYS[key];
    return p ? p[lang()] || p.ru : t(key, params);
  }

  // Запасные тексты, если не загрузился даже словарь (i18n.js): ru + kk в одной строке (R10 B-006).
  var BARE = {
    loading: "Загружаем… / Жүктелуде…",
    error: "Не получилось загрузить. / Жүктелмеді.",
    empty: "Пока пусто / Әзірге бос",
    retry: "Повторить / Қайталау",
    kit: "Не загрузились файлы интерфейса. Обновите страницу. / Интерфейс файлдары жүктелмеді. Бетті жаңартыңыз.",
  };
  function bare(key, text) {
    var i18n = I();
    return i18n && i18n.has && i18n.has(key) ? i18n.t(key) : text;
  }

  // Состояние блока: ui-kit (BirgeUI.state), а если он не загрузился — простой текст и «Повторить»,
  // чтобы не было пустого экрана (UX_BRIEF, правило 7; R10 B-006).
  function stateBox(el, kind, opts) {
    opts = opts || {};
    if (root.BirgeUI) {
      root.BirgeUI.state(el, kind, opts);
      return;
    }
    var text = opts.text || opts.title || (kind === "loading" ? bare("common.state.loading", BARE.loading)
      : kind === "error" ? bare("common.state.error_title", BARE.error) : bare("common.state.empty_title", BARE.empty));
    el.innerHTML = '<p class="r06-bare" role="' + (kind === "error" ? "alert" : "status") + '">' + esc(text) + "</p>" +
      (kind === "error" && opts.action ? '<button class="r06-bare__btn" type="button">' +
        esc(bare("common.action.retry", BARE.retry)) + "</button>" : "");
    var btn = el.querySelector(".r06-bare__btn");
    if (btn) btn.addEventListener("click", opts.action.onClick);
  }

  function mount(el, load, render, notFoundKey) {
    if (!I()) {
      // Без словаря карточка показала бы сырые ключи — честно говорим, что интерфейс не загрузился.
      stateBox(el, "error", { title: BARE.kit, action: { onClick: function () { root.location.reload(); } } });
      return Promise.resolve();
    }
    function go() {
      stateBox(el, "loading");
      return load().then(render, function (err) {
        if (err.status === 404) stateBox(el, "empty", { title: t(notFoundKey) });
        else stateBox(el, "error", { action: { onClick: go } });
      });
    }
    var start = I() ? I().ready.then(go) : go();
    return start;
  }

  function mountProposal(el, id, opts) {
    return mount(el, function () { return api.proposal(id); }, function (data) { return renderProposal(el, data.item, opts); }, "proposal.not_found");
  }

  // ── Этапы объекта ──
  function stagesHtml(o) {
    if (o.stage == null || STAGES.indexOf(o.stage) < 0) {
      return '<p class="bk-section-title">' + esc(t("stage.title")) + '</p><p class="r06-stage-unknown">' + esc(t("object.stage_unknown")) + "</p>";
    }
    var current = STAGES.indexOf(o.stage);
    var items = STAGES.map(function (s, i) {
      var st = i < current || (o.stage === "operating" && i === current) ? "done" : i === current ? "current" : "todo";
      return '<li data-state="' + st + '"' + (i === current ? ' aria-current="step"' : "") + "><span>" + esc(t("stage." + s)) + "</span></li>";
    }).join("");
    var badges = [];
    if (o.late) badges.push('<span class="bk-tag bk-tag--warn">' + icon("clock") + "<span>" + esc(t("object.late", { n: o.delay_days })) + "</span></span>");
    else if (o.stage !== "operating" && o.delay_days === 0) badges.push('<span class="bk-tag">' + icon("check") + "<span>" + esc(t("object.on_time")) + "</span></span>");
    if (o.stale) badges.push('<span class="bk-tag">' + icon("alert") + "<span>" + esc(t("object.stale_days", { n: o.stale_days })) + "</span></span>");
    var dates = [];
    if (o.planned_end) dates.push(esc(t("object.planned_end", { date: date(o.planned_end) })));
    if (o.forecast_end && o.forecast_end !== o.planned_end) dates.push(esc(t("object.forecast_end", { date: date(o.forecast_end) })));
    if (o.last_update_at) dates.push(esc(t("object.updated", { date: date(o.last_update_at) })));
    return (
      '<p class="bk-section-title">' + esc(t("stage.title")) + "</p>" +
      '<ol class="bk-stages' + (o.late ? " bk-stages--late" : "") + '">' + items + "</ol>" +
      '<p class="bk-stages__caption">' + esc(t("stage.caption", { i: current + 1, total: STAGES.length, name: t("stage." + o.stage) })) + "</p>" +
      (badges.length ? '<div class="bk-card__row">' + badges.join("") + "</div>" : "") +
      (dates.length ? '<p class="bk-meta r06-dates">' + dates.join("<br>") + "</p>" : "")
    );
  }

  function renderStages(el, object) {
    el.classList.add("r06-stages"); // отступы блока этапов (proposals.css)
    function draw() {
      el.innerHTML = stagesHtml(object);
    }
    draw();
    if (I()) I().onChange(draw);
  }

  function objectHtml(o) {
    var id = "r06-o-" + esc(o.id);
    return (
      '<article class="bk-card r06-card" aria-labelledby="' + id + '" data-object="' + esc(o.id) + '">' +
      '<div class="bk-card__row"><span class="bk-card__eyebrow">' + icon(OBJECT_ICON[o.kind] || "building") + "<span>" +
      esc(t("object.kind." + o.kind)) + "</span></span>" +
      (o.demo ? '<span class="bk-tag bk-tag--demo" title="' + esc(t("common.tag.demo_hint")) + '">' + esc(t("common.tag.demo")) + "</span>" : "") +
      (o.geometry_precision === "approximate" ? '<span class="bk-tag bk-tag--approx">' + esc(t("common.tag.approx")) + "</span>" : "") +
      "</div>" +
      // Название объекта в civic-v1 одно (на языке источника, lang="ru"); title_kk есть только у демо-записей.
      (lang() === "kk" && o.title_kk
        ? '<h3 class="bk-card__title" id="' + id + '" lang="kk">' + esc(o.title_kk) + "</h3>"
        : '<h3 class="bk-card__title" id="' + id + '" lang="ru">' + esc(o.demo ? demoTitle(o.title) : o.title) + "</h3>") +
      (o.district ? '<p class="bk-meta" style="margin:0">' + esc(t("district.name", { name: t("district." + o.district) })) + "</p>" : "") +
      '<hr class="bk-divider" /><div class="r06-stages">' + stagesHtml(o) + "</div></article>"
    );
  }

  function renderObject(el, object) {
    function draw() {
      el.innerHTML = objectHtml(object);
    }
    draw();
    if (I()) I().onChange(draw);
    return { get: function () { return object; }, redraw: draw };
  }

  function mountObject(el, id) {
    return mount(el, function () { return api.object(id); }, function (data) { return renderObject(el, data.item); }, "object.not_found");
  }

  root.BirgeProposals = {
    api: api,
    unwrap: unwrap,
    deviceId: deviceId,
    renderProposal: renderProposal,
    mountProposal: mountProposal,
    renderObject: renderObject,
    mountObject: mountObject,
    renderStages: renderStages,
    stagesHtml: stagesHtml,
    demoTitle: demoTitle,
    stateBox: stateBox,
    KIT_MISSING: BARE.kit,
    STAGES: STAGES.slice(),
  };
})(typeof self !== "undefined" ? self : this);
