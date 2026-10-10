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

  // Ключи, которых ещё нет в словарях R11 (переданы в research/round-14-results/R06/INTEGRATION.txt).
  // Пока R11 их не добавил, берём текст отсюда; как только ключ есть в ru.json/kk.json — побеждает словарь.
  var PENDING = {
    "proposal.your_vote_up": { ru: "Вы проголосовали «за»", kk: "Сіз «жақтаймын» деп дауыс бердіңіз" },
    "proposal.your_vote_down": { ru: "Вы проголосовали «против»", kk: "Сіз «қарсымын» деп дауыс бердіңіз" },
    "proposal.vote_saved": { ru: "Голос учтён", kk: "Дауысыңыз есепке алынды" },
    "proposal.vote_changed": { ru: "Голос изменён", kk: "Дауысыңыз өзгертілді" },
    "proposal.vote_error": {
      ru: "Не удалось отправить голос. Проверьте связь и повторите.",
      kk: "Дауыс жіберілмеді. Байланысты тексеріп, қайталаңыз.",
    },
    "proposal.voting_closed": { ru: "Голосование по этому проекту закрыто", kk: "Бұл жоба бойынша дауыс беру аяқталды" },
    "proposal.votes_aria": { ru: "За: {up}, против: {down}", kk: "Жақтағандар: {up}, қарсылар: {down}" },
    "proposal.need_staff": { ru: "Войдите как сотрудник акимата", kk: "Әкімдік қызметкері ретінде кіріңіз" },
    "proposal.already_decided": {
      ru: "Решение по проекту уже принято. Карточка обновлена.",
      kk: "Жоба бойынша шешім қабылданып қойған. Ақпарат жаңартылды.",
    },
    "proposal.not_found": { ru: "Проект не найден или снят", kk: "Жоба табылмады немесе алынып тасталды" },
    "object.stage_unknown": { ru: "Этап работ не указан", kk: "Жұмыс кезеңі көрсетілмеген" },
    "object.not_found": { ru: "Объект не найден или снят с публикации", kk: "Нысан табылмады немесе жариялаудан алынды" },
    "object.kind.construction": { ru: "Строительство", kk: "Құрылыс" },
    "object.kind.roadworks": { ru: "Ремонт дороги", kk: "Жол жөндеу" },
    "object.kind.landscaping": { ru: "Благоустройство", kk: "Абаттандыру" },
    "object.kind.event": { ru: "Мероприятие", kk: "Іс-шара" },
  };

  function I() {
    return root.BirgeI18n;
  }
  function lang() {
    return I() ? I().getLang() : "ru";
  }
  function fill(text, params) {
    return String(text).replace(/\{(\w+)\}/g, function (m, name) {
      if (!params || params[name] === undefined || params[name] === null) return m;
      var v = params[name];
      return typeof v === "number" && I() ? I().formatNumber(v) : String(v);
    });
  }
  function t(key, params) {
    var i18n = I();
    if (i18n && i18n.has(key)) return i18n.t(key, params);
    var p = PENDING[key];
    if (p) return fill(p[lang()] || p.ru, params);
    return i18n ? i18n.t(key, params) : key; // покажет ключ и предупредит в консоли — видно на проверке
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

  // ── Предложение ──
  function title(p) {
    // Казахское название, если акимат его ввёл; иначе русское с lang="ru" (экранный диктор прочтёт верно).
    if (lang() === "kk" && p.title_kk) return { text: p.title_kk, lang: "kk" };
    return { text: p.title_ru, lang: "ru" };
  }

  function proposalHtml(p, opts) {
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
      '<div class="r06-vote" role="group" aria-label="' + esc(t("proposal.votes_aria", { up: p.votes_up, down: p.votes_down })) + '">' +
      voteBtn(1, "proposal.vote_up", "thumb-up", p.votes_up) + voteBtn(-1, "proposal.vote_down", "thumb-down", p.votes_down) + "</div>" +
      '<div class="r06-share" aria-hidden="true"><i class="r06-share__up" style="width:' + upShare + '%"></i><i class="r06-share__down" style="width:' +
      (total ? 100 - upShare : 0) + '%"></i></div>' +
      '<p class="bk-meta r06-vote__note" aria-live="polite">' + esc(note) + "</p>";
    if (opts.role === "akimat" && p.status === "proposal") {
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

  function stateBox(el, kind, opts) {
    if (root.BirgeUI) root.BirgeUI.state(el, kind, opts);
  }

  function mount(el, load, render, notFoundKey) {
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
      // Название объекта в civic-v1 одно (на языке источника) — помечаем lang="ru".
      '<h3 class="bk-card__title" id="' + id + '" lang="ru">' + esc(o.title) + "</h3>" +
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
    PENDING_KEYS: Object.keys(PENDING),
    STAGES: STAGES.slice(),
  };
})(typeof self !== "undefined" ? self : this);
