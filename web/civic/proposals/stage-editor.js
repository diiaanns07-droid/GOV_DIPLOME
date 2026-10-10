/*
 * R06 · блок «Этап работ» для кабинета сотрудника (раунд 14).
 *
 * Редактор объектов принадлежит R12 (web/civic/editor/). Чтобы не менять его форму и сохранение,
 * этап — отдельный блок со своей кнопкой и своей ревизией (stage_revision). Подключение в редакторе —
 * несколько строк, patch в research/round-14-results/R06/INTEGRATION.txt:
 *
 *   BirgeStageEditor.mount(container, { objectId: "ast-…", readOnly: false, onSaved: fn })
 *
 * Запросы: GET /api/civic/v2/staff/objects/{id}/stage, PUT /api/civic/v2/objects/{id}/stage
 * (CSRF — из GET /api/civic/v1/session; cookie сессии с раунда 14 действует на весь /api/civic).
 * Нужны ui-kit (tokens.css, components.css) и, по возможности, i18n.js и ui-kit.js.
 */
(function (root) {
  "use strict";

  var STAGES = ["planned", "design", "procurement", "construction", "acceptance", "operating"];
  // Все тексты — из словарей R11 (web/civic/i18n, ветка claude/r14-R11): 33 ключа R06 там с 12 октября.
  // Запасной список PENDING убран (STATUS R06, «следующий шаг»): нет ключа — i18n покажет ключ и предупредит.

  function I() {
    return root.BirgeI18n;
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

  function request(method, path, body, csrf) {
    var headers = { Accept: "application/json" };
    if (body) headers["Content-Type"] = "application/json";
    if (csrf) headers["X-CSRF-Token"] = csrf;
    return root.fetch(path, { method: method, credentials: "same-origin", headers: headers, body: body ? JSON.stringify(body) : undefined }).then(
      function (res) {
        return res.json().then(function (json) {
          // Конверт {ok, data} (R02/R06) или «голый» JSON шлюза R01 — как в proposals.js.
          if (res.ok && json && json.ok === true) return json.data;
          if (res.ok && json && json.ok === undefined && !json.error) return json;
          var e = (json && json.error) || {};
          var err = new Error((typeof e === "object" ? e.message : json.message) || "HTTP " + res.status);
          err.status = res.status;
          err.code = typeof e === "string" ? e : e.code;
          err.fields = (typeof e === "object" && e.fields) || json.fields || {};
          throw err;
        });
      },
      function () {
        var err = new Error("network");
        err.status = 0;
        err.code = "network";
        throw err;
      }
    );
  }

  // Дата словами под полем: «23 ноя 2026» / «23 қараша 2026». Формат самого поля type="date" задаёт язык
  // браузера (в облачном Chromium — 11/23/2026 при любом языке страницы), поэтому подпись снимает двусмысленность
  // «11/23 или 23.11» независимо от браузера (UX_REVIEW R11, день 3, п. 18).
  function words(iso) {
    return iso && I() ? I().formatDate(iso, { year: true }) : "";
  }

  var seq = 0;
  function mount(el, opts) {
    // Без ui-kit — простой текст (общая функция карточек R06, если подключена), а не пустой блок (R10 B-006).
    function state(kind, o) {
      if (root.BirgeUI) root.BirgeUI.state(el, kind, o);
      else if (root.BirgeProposals && root.BirgeProposals.stateBox) root.BirgeProposals.stateBox(el, kind, o);
    }
    opts = opts || {};
    var id = opts.objectId;
    var P = "r06-se-" + ++seq + "-";
    var S = { item: null, busy: false, errors: {}, message: null, tone: "info", draft: null };

    function draw() {
      var it = S.item;
      if (!it) return;
      var d = S.draft;
      var ro = !!opts.readOnly;
      var options = '<option value="">' + esc(t("stage.editor.select")) + "</option>" + STAGES.map(function (s) {
        return '<option value="' + s + '"' + (d.stage === s ? " selected" : "") + ">" + esc(t("stage." + s)) + "</option>";
      }).join("");
      var err = function (name) {
        return S.errors[name] ? '<p class="bk-field__error" id="' + P + name + '-err">' + esc(S.errors[name]) + "</p>" : "";
      };
      var invalid = function (name) {
        return S.errors[name] ? ' aria-invalid="true" aria-describedby="' + P + name + '-err"' : "";
      };
      var status = "";
      if (it.late) status = '<span class="bk-tag bk-tag--warn">' + esc(t("object.late", { n: it.delay_days })) + "</span>";
      else if (it.stage && it.stage !== "operating" && it.delay_days === 0) status = '<span class="bk-tag">' + esc(t("object.on_time")) + "</span>";
      if (it.stale) status += ' <span class="bk-tag">' + esc(t("object.stale_days", { n: it.stale_days })) + "</span>";
      el.innerHTML =
        '<section class="bk-card r06-stage-editor" aria-labelledby="' + P + 'h">' +
        '<h4 class="bk-card__title" id="' + P + 'h">' + esc(t("stage.editor.title")) + "</h4>" +
        (it.publication === "draft" ? '<p class="bk-meta" style="margin:0">' + esc(t("stage.editor.draft_note")) + "</p>" : "") +
        (status ? '<div class="bk-card__row">' + status + "</div>" : "") +
        '<fieldset class="r06-stage-editor__fields"' + (ro ? " disabled" : "") + ">" +
        '<div class="bk-field' + (S.errors.stage ? " bk-field--error" : "") + '"><label class="bk-field__label" for="' + P + 'stage">' + esc(t("stage.editor.stage")) +
        '</label><select class="bk-field__input" id="' + P + 'stage" name="stage"' + invalid("stage") + ">" + options + "</select>" + err("stage") + "</div>" +
        '<div class="bk-field' + (S.errors.planned_end ? " bk-field--error" : "") + '"><label class="bk-field__label" for="' + P + 'planned">' + esc(t("stage.editor.planned_end")) +
        '</label><input class="bk-field__input" type="date" id="' + P + 'planned" name="planned_end" value="' + esc(d.planned_end || "") + '"' + invalid("planned_end") +
        ' /><p class="bk-field__hint r06-date-words" data-words-for="planned_end">' + esc(words(d.planned_end)) + "</p>" + '<p class="bk-field__hint">' + esc(t("stage.editor.planned_hint")) + "</p>" + err("planned_end") + "</div>" +
        '<div class="bk-field' + (S.errors.forecast_end ? " bk-field--error" : "") + '"><label class="bk-field__label" for="' + P + 'forecast">' + esc(t("stage.editor.forecast_end")) +
        '</label><input class="bk-field__input" type="date" id="' + P + 'forecast" name="forecast_end" value="' + esc(d.forecast_end || "") + '"' + invalid("forecast_end") +
        ' /><p class="bk-field__hint r06-date-words" data-words-for="forecast_end">' + esc(words(d.forecast_end)) + "</p>" + '<p class="bk-field__hint">' + esc(t("stage.editor.forecast_hint")) + "</p>" + err("forecast_end") + "</div>" +
        '<div class="bk-field"><label class="bk-field__label" for="' + P + 'reason">' + esc(t("stage.editor.reason")) +
        '</label><textarea class="bk-field__input" rows="2" id="' + P + 'reason" name="reason"' + invalid("reason") + ">" + esc(d.reason || "") + "</textarea>" + err("reason") + "</div>" +
        '<button class="bk-btn bk-btn--primary" type="button" data-save' + (S.busy ? ' aria-busy="true" disabled' : "") + ">" +
        esc(t(S.busy ? "stage.editor.saving" : "stage.editor.save")) + "</button>" +
        "</fieldset>" +
        '<p class="bk-meta" role="status" aria-live="polite" data-msg>' + esc(S.message || "") + "</p>" +
        "</section>";
    }

    function readForm() {
      ["stage", "planned_end", "forecast_end", "reason"].forEach(function (name) {
        var input = el.querySelector('[name="' + name + '"]');
        if (input) S.draft[name] = input.value;
      });
    }

    function fromItem(it) {
      S.item = it;
      S.draft = { stage: it.stage || "", planned_end: it.planned_end || "", forecast_end: (it.forecast_source === "editor" && it.forecast_end) || "", reason: "" };
    }

    function load() {
      state("loading");
      return request("GET", "/api/civic/v2/staff/objects/" + encodeURIComponent(id) + "/stage").then(
        function (data) {
          fromItem(data.item);
          draw();
        },
        function (e) {
          state("error", { text: t(e.status === 401 ? "stage.editor.login" : "stage.editor.error"), action: { onClick: load } });
        }
      );
    }

    function save() {
      if (S.busy) return;
      readForm();
      S.busy = true;
      S.errors = {};
      S.message = null;
      draw();
      var body = {
        expected_revision: S.item.stage_revision,
        stage: S.draft.stage || null,
        planned_end: S.draft.planned_end || null,
        forecast_end: S.draft.forecast_end || null,
      };
      if (S.draft.reason && S.draft.reason.trim()) body.reason = S.draft.reason;
      request("GET", "/api/civic/v1/session")
        .then(function (sess) {
          if (!sess.authenticated) {
            var e = new Error("unauthenticated");
            e.status = 401;
            throw e;
          }
          // PUT — как в CONTRACT §7 и таблице шлюза R01 (сервис R06 принимает и POST).
          return request("PUT", "/api/civic/v2/objects/" + encodeURIComponent(id) + "/stage", body, sess.csrf_token);
        })
        .then(
          function (data) {
            S.busy = false;
            fromItem(data.item);
            S.message = t(data.changed ? "stage.editor.saved" : "stage.editor.unchanged");
            draw();
            if (root.BirgeUI) root.BirgeUI.toast(S.message);
            if (opts.onSaved) opts.onSaved(data.item);
          },
          function (e) {
            S.busy = false;
            if (e.status === 409) {
              // Чужая правка: показываем свежую версию, введённое сотрудником не сохраняем молча.
              return request("GET", "/api/civic/v2/staff/objects/" + encodeURIComponent(id) + "/stage").then(function (data) {
                fromItem(data.item);
                S.message = t("stage.editor.conflict");
                draw();
              });
            }
            if (e.status === 422) {
              S.errors = e.fields || {};
              S.message = t("stage.editor.fix");
            } else {
              S.message = t(e.status === 401 || e.code === "csrf_failed" ? "stage.editor.login" : "stage.editor.error");
            }
            draw();
            var first = el.querySelector('[aria-invalid="true"]');
            if (first) first.focus();
          }
        );
    }

    el.addEventListener("input", function (e) {
      var name = e.target && e.target.getAttribute("name");
      var out = name && el.querySelector('[data-words-for="' + name + '"]');
      if (out) out.textContent = words(e.target.value);
    });
    el.addEventListener("click", function (e) {
      var b = e.target.closest && e.target.closest("[data-save]");
      if (b && !b.disabled) save();
    });
    if (I()) I().onChange(function () {
      if (S.item) {
        readForm();
        draw();
      }
    });
    var ready = I() ? I().ready.then(load) : load();
    return { reload: load, ready: ready };
  }

  root.BirgeStageEditor = { mount: mount };
})(typeof self !== "undefined" ? self : this);
