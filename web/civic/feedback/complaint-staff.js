/*
 * R09 · волна 2 · Действия сотрудника по одной жалобе (R11 IA_WAVE2 §2.3–2.4). Встраивают R07 в карточку цели,
 * R09 в «Обращения» акимата (complaint-list.js). Новых слоёв карты нет: компонент живёт в карточке.
 *   «Сообщить жителям об устранении» — одна строка «что сделали» (обязательно) + 1 фото «после» (п. 1);
 *   паспорт решения — «Изменить» → 3 поля: кто отвечает, следующий шаг, ориентир устранения; при просрочке —
 *   ещё причина, временная мера, следующее обновление (п. 2);
 *   «Обновление для всех» — одно сообщение автору и всем «Я тоже» (п. 3). Перед действием — «Увидят N человек».
 *
 *   BirgeComplaintStaff.mount(container, { complaintId, csrf: "<токен R02>" | () => токен, onChange(complaint),
 *                                         fix: false (без «Отметить исправленным»), compact, staffOnly })
 *     -> { refresh(), destroy() }
 *   BirgeComplaintStaff.fixForm(container, { complaintIds, csrf, onDone, onCancel }) — форма для карточки цели R07.
 * Тексты — словарь R11 (fix.*, passport.*, broadcast.*, service.*), запасной — complaint-strings.js.
 *
 * Раунд 15 (CONTRACT §5.1) — блок «Службы» над главной кнопкой: подсказка R04 «Похоже, нужны 2 службы» (принять
 * одним нажатием), части служб со статусом (ждёт · в работе · сделано), «Передать в другую службу» (причина — чипы +
 * строка; срок ответа жителю не начинается заново), «Совместное исполнение» (добавить службу), передачи свёрнуты в
 * «Передачи». «Черновик ответа» (R04 POST /reply-draft) заполняет «Обновление для всех» — сотрудник правит и отправляет.
 */
(function () {
  "use strict";
  var API = "/api/civic/v2";
  var WHAT_DONE_MAX = 120;   // R11 §2.3: «Что сделали» — одна строка, ≤ 120 знаков
  var C = function () { return window.BirgeComplaint; };
  var t = function (key, params) { return C().t(key, params); };

  function h(tag, attrs, children) {
    var el = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (key) {
      var value = attrs[key];
      if (value === null || value === undefined || value === false) return;
      if (key === "class") el.className = value;
      else if (key.slice(0, 2) === "on") el.addEventListener(key.slice(2), value);
      else el.setAttribute(key, value === true ? "" : value);
    });
    [].concat(children === undefined ? [] : children).forEach(function (child) {
      if (child === null || child === undefined || child === false) return;
      el.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
    });
    return el;
  }

  function services() {
    return ((window.BirgeCategoriesV2 || {}).services) || [];
  }

  function serviceLabel(id, fallback) {
    var label = id ? t("service." + id) : "";
    return label || fallback || "";
  }

  function dateText(day) {
    return C().formatDate(day + "T12:00:00+05:00");
  }

  // Статус части службы → значок ui-kit: ждёт — пустой круг, в работе — половина, сделано — круг с галочкой
  // (как «служба сообщила»; зелёная заливка — только «проверено жителями»).
  var PART_ICON = { todo: "new", in_progress: "in_progress", done: "reported_fixed" };
  var PART_STATUSES = ["todo", "in_progress", "done"];
  var REASONS = ["other_service", "first_other_work", "not_our_zone", "wrong_category"];
  function partIcon(status) { return C().statusIcon ? C().statusIcon(PART_ICON[status] || "new") : null; }
  function joinNames(ids) {
    var names = ids.map(function (sid) { return serviceLabel(sid, sid); });
    if (names.length < 2) return names.join("");
    return names.slice(0, -1).join(", ") + t("joint.and") + names[names.length - 1];
  }

  // Какие маршруты v2 подключены в сборке: GET /modules шлюза R01 (один раз на страницу). Кнопка «Черновик ответа»
  // видна, только если маршрут R04 reply-draft готов — без него не будет ни кнопки, ни 404 в консоли.
  var modulesPromise = null;
  function modules() {
    if (!modulesPromise) {
      modulesPromise = fetch(API + "/modules", { credentials: "same-origin", headers: { "Accept": "application/json" } })
        .then(function (r) { return r.ok ? r.json() : null; }, function () { return null; })
        .then(function (j) { return (j && (j.modules || (j.data && j.data.modules))) || {}; }, function () { return {}; });
    }
    return modulesPromise;
  }
  function draftReady(list) {
    return Object.keys(list || {}).some(function (key) {
      return /reply/.test(key) && list[key] && list[key].status === "ready";
    });
  }

  // Маршруты-функции R04 (POST /reply-draft) отвечают голым JSON шлюза v2 (без конверта ok/data).
  function rawCall(path, body, csrf) {
    return fetch(API + path, { method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "Accept": "application/json", "X-CSRF-Token": csrf || "" },
      body: JSON.stringify(body) })
      .then(function (r) { return r.json().catch(function () { return null; }).then(function (j) {
        return { ok: r.ok && !!j && !j.error, status: r.status, body: j };
      }); }, function () { return { ok: false, status: 0 }; });
  }

  function mount(container, opts) {
    opts = opts || {};
    var id = opts.complaintId;
    var csrf = function () { return typeof opts.csrf === "function" ? opts.csrf() : (opts.csrf || ""); };
    var root = h("section", { "class": "bc-staff", "aria-label": t("staff.title") });
    var uid = Math.random().toString(36).slice(2, 8);   // id подсказки поля (aria-describedby) — свой у каждой карточки
    container.appendChild(root);
    var current = null;
    var photo = null;
    var editing = false;
    // R11 §2.3: «Отметить исправленным» открывает форму в той же карточке (не модальное окно); opts.openFix — сразу
    // с формой (выбрали «Отметить исправленным» в меню статуса строки «Обращений»).
    var fixing = !!opts.openFix;
    var lastNote = null;
    // Блок «Службы» (раунд 15): какая форма открыта, скрыта ли подсказка R04, подсказка, полученная по запросу.
    var jointUi = { form: null, hintHidden: false, noteFor: opts.openPart || null, draft: "idle" };

    function call(method, path, body) {
      return fetch(API + path, { method: method, credentials: "same-origin",
        headers: { "Content-Type": "application/json", "Accept": "application/json", "X-CSRF-Token": csrf() },
        body: body === undefined ? undefined : JSON.stringify(body) })
        .then(function (r) { return r.json().catch(function () { return null; }).then(function (j) {
          return { ok: r.ok && j && j.ok !== false, status: r.status, data: j && j.data, error: j && j.error };
        }); }, function () { return { ok: false, status: 0 }; });
    }

    function note(text, isError) {
      lastNote = { text: text, error: !!isError };
      var box = root.querySelector(".bc-staff__note");
      if (!box) return;
      box.textContent = text;
      box.setAttribute("role", isError ? "alert" : "status");
      box.className = "bc-staff__note" + (isError ? " bc-staff__note--error" : "");
    }

    function done(res) {
      if (!res || !res.ok) { note((res && res.error && res.error.message) || t("complaint.error.send"), true); return false; }
      current = res.data.complaint;
      editing = false;
      fixing = false;
      if (typeof opts.onChange === "function") opts.onChange(current);
      lastNote = { text: t("fix.will_see", { n: res.data.notified || 0 }), error: false };
      render();
      return true;
    }

    // Ошибка — прямо в форме, над кнопкой (внизу карточки её не видно, R10 B-056).
    function fixError(form, text) {
      var box = form.querySelector(".bc-staff__fix-error");
      if (!text) { if (box) box.parentNode.removeChild(box); return; }
      if (!box) {
        box = h("p", { "class": "bc-staff__fix-error", role: "alert" });
        form.insertBefore(box, form.querySelector("button[type=submit]"));
      }
      box.textContent = text;
    }

    function markFixed(form) {
      var what = form.querySelector("[name=what_done]").value.trim();
      if (what.length < 3) { fixError(form, t("staff.fixed.need_what")); return; }
      var button = form.querySelector("button[type=submit]");
      button.disabled = true;
      fixError(form, null);
      // R10 B-056: фото — сам Blob после уменьшения, без fetch(blob:…) (CSP сборки: connect-src 'self').
      var upload = photo
        ? window.BirgeComplaintPhotos.upload(id, photo.blob, "after", csrf()).then(null, function () { throw { photo: true }; })
        : Promise.resolve(null);
      upload.then(function (uploaded) {
        var steps = current && current.status === "new" ? call("POST", "/complaints/" + id + "/status", { status: "in_progress" })
          : Promise.resolve({ ok: true });
        return steps.then(function () {
          return call("POST", "/complaints/" + id + "/status",
                      { status: "fixed", what_done: what, photos: uploaded ? [uploaded.id] : [] });
        });
      }).then(function (res) {
        button.disabled = false;
        if (res && res.ok) {
          if (photo && photo.url) URL.revokeObjectURL(photo.url);
          photo = null; done(res); return;
        }
        fixError(form, (res && res.error && res.error.message) || t("complaint.error.send"));
      }, function (err) {
        button.disabled = false;
        fixError(form, t(err && err.photo ? "staff.photo.failed" : "complaint.error.send"));
      });
    }

    function savePassport(form) {
      var get = function (name) { var f = form.querySelector("[name=" + name + "]"); return f ? f.value.trim() : undefined; };
      var body = { service: get("service"), next_step: get("next_step"), fix_eta: get("fix_eta") };
      if (form.querySelector("[name=delay_reason]")) {
        body.delay_reason = get("delay_reason"); body.temp_measure = get("temp_measure"); body.next_update_at = get("next_update_at");
        // «Нужно решение руководителя» → блок R08 «Нужно решение акима» (волна 2 п. 5): два варианта и что нужно.
        var needs = form.querySelector("[name=needs_decision]");
        body.needs_decision = !!(needs && needs.checked);
        if (body.needs_decision) {
          body.option_1 = get("option_1"); body.option_2 = get("option_2"); body.decision = get("decision");
        }
      }
      call("POST", "/complaints/" + id + "/passport", body).then(done);
    }

    function postUpdate(form) {
      var text = form.querySelector("[name=text]").value.trim();
      call("POST", "/complaints/" + id + "/update", { text: text }).then(function (res) {
        if (done(res)) form.reset();
      });
    }

    // Пример под полем — строкой, а не подсказкой внутри поля: на 375 она обрезалась и пропадает при вводе (R10 круг 2).
    function field(label, input, hint, hintId) {
      return h("label", { "class": "bc-staff__field" }, [h("span", { "class": "bc-label" }, label), input,
        hint ? h("span", { "class": "bc-meta bc-staff__hint", id: hintId || null }, hint) : null]);
    }

    function isOpen() {
      return current && (current.status === "new" || current.status === "accepted" || current.status === "in_progress");
    }

    function delayed() {
      var p = current.passport_view || {};
      return !!(p.delay || p.update_overdue || (current.deadline && current.deadline.state === "overdue"));
    }

    function passportSummary() {
      var p = current.passport_view || {};
      var lines = [t("service.assigned", { service: serviceLabel(p.assignee_custom ? null : p.assignee_id, p.assignee) }),
                   t("passport.next", { text: p.next_step || t("mine.passport.next_default." + current.status) }),
                   p.fix_eta ? t("passport.fix_eta", { date: dateText(p.fix_eta) }) : t("passport.fix_unknown")];
      var d = p.delay || {};
      if (d.reason) lines.push(t("passport.delay_reason", { text: d.reason }));
      if (d.temp_measure) lines.push(t("passport.temp_measure", { text: d.temp_measure }));
      if (d.next_update_at) lines.push(t("passport.next_update", { date: dateText(d.next_update_at) }));
      if (d.needs_decision) {
        lines.push(t("akim.decision.title") + (d.decision ? " · " + t("akim.decision.needed", { text: d.decision }) : ""));
        (d.options || []).forEach(function (o, i) { lines.push(t("akim.decision.option", { n: i + 1, text: o.ru || o.kk || "" })); });
        if ((d.options || []).length < 2) lines.push(t("akim.decision.no_options"));
        if (p.decision_choice) lines.push(t("akim.decision.chosen", { n: p.decision_choice.option }));
      }
      return h("ul", { "class": "bc-passport" }, lines.map(function (line) { return h("li", {}, line); }));
    }

    function passportForm() {
      var p = current.passport_view || {};
      var stored = current.passport || {};
      var d = p.delay || {};
      var select = h("select", { name: "service" }, [h("option", { value: "" }, serviceLabel(p.assignee_id, p.assignee))]);
      services().forEach(function (s) {
        select.appendChild(h("option", { value: s.id, selected: stored.assignee_id === s.id ? true : null },
          serviceLabel(s.id, s.ru)));
      });
      var fields = [
        field(t("passport.field.service"), select),
        field(t("passport.field.next"), h("input", { name: "next_step", maxlength: "160", value: p.next_step || "" })),
        field(t("passport.field.eta"), h("input", { name: "fix_eta", type: "date", value: p.fix_eta || "" }))];
      // Ещё 3 поля — только при задержке (просрочен срок или обещанное обновление), R11 §2.3.
      if (delayed()) {
        var next = h("input", { name: "next_update_at", type: "date", value: d.next_update_at || "" });
        var reason = h("input", { name: "delay_reason", maxlength: "160", value: d.reason || "" });
        reason.addEventListener("input", function () { next.required = !!reason.value.trim(); });
        next.required = !!(d.reason || "");
        fields.push(field(t("passport.field.reason"), reason),
                    field(t("passport.field.temp"), h("input", { name: "temp_measure", maxlength: "160", value: d.temp_measure || "" })),
                    field(t("passport.field.next_update"), next));
        // Задержку не сдвинуть без руководителя: два варианта и что нужно от акима (R08 «Нужно решение акима»).
        var opts = d.options || [];
        var extra = h("div", { "class": "bc-staff__decision", hidden: d.needs_decision ? null : true }, [
          field(t("passport.field.option", { n: 1 }), h("input", { name: "option_1", maxlength: "160", value: (opts[0] || {}).ru || "" })),
          field(t("passport.field.option", { n: 2 }), h("input", { name: "option_2", maxlength: "160", value: (opts[1] || {}).ru || "" })),
          field(t("passport.field.decision"), h("input", { name: "decision", maxlength: "160", value: d.decision || "" }))]);
        var box = h("input", { type: "checkbox", name: "needs_decision", checked: d.needs_decision ? true : null });
        box.addEventListener("change", function () { extra.hidden = !box.checked; });
        fields.push(h("label", { "class": "bc-staff__check" }, [box, h("span", {}, t("passport.field.needs_decision"))]), extra);
      }
      var form = h("form", { "class": "bc-staff__form bc-staff__passport-form",
                             onsubmit: function (e) { e.preventDefault(); savePassport(form); } },
        fields.concat([h("button", { "class": "bk-btn bk-btn--block", type: "submit" }, t("common.action.save"))]));
      return form;
    }

    // ---------------------------------------------------------------- раунд 15: несколько служб (CONTRACT §5.1)
    function jointInfo() { return current && current.joint && current.joint.services ? current.joint : null; }

    function jointDone(res, message) {
      if (!res || !res.ok) {
        note((res && res.error && res.error.message) || t("complaint.error.send"), true);
        render();
        return false;
      }
      current = res.data.complaint;
      jointUi.form = null; jointUi.noteFor = null;
      if (typeof opts.onChange === "function") opts.onChange(current);
      lastNote = { text: message || t("fix.will_see", { n: res.data.notified || 0 }), error: false };
      render();
      return true;
    }

    function setPart(service, status, text) {
      var part = (jointInfo().services || []).filter(function (p) { return p.service === service; })[0] || {};
      var body = { service: service, status: status, expected: part.status };
      if (text !== undefined) body.note = text;
      return call("POST", "/complaints/" + id + "/part", body).then(function (res) {
        jointDone(res, t("joint.part.saved", { service: serviceLabel(service), status: t("joint.part." + status) }));
      });
    }

    function setServices(list, message) {
      var lead = jointInfo().lead;
      return call("POST", "/complaints/" + id + "/services", { services: list, expected_lead: lead }).then(function (res) {
        jointDone(res, message);
      });
    }

    // Подсказка R04 «нужны 2 службы» — из записи: сервер R09 зовёт route() R04 в процессе при подаче (route_hint) и
    // берёт её из демо-мира R02. Отдельного запроса POST /route с экрана нет: пока маршрута нет в сборке, он давал бы
    // 404 в консоли (приёмка R10 считает такие ошибки).
    function routeHint() {
      var j = jointInfo();
      return j.route_hint && j.route_hint.services ? j.route_hint : null;
    }

    function hintBanner(j) {
      var hint = routeHint();
      if (!hint || jointUi.hintHidden || !isOpen() || (hint.services || []).length < 2) return null;
      var now = (j.services || []).map(function (p) { return p.service; });
      var same = hint.services.length === now.length && hint.services.every(function (sid) { return now.indexOf(sid) >= 0; });
      if (same || hint.accepted_at) return null;
      var why = C().lang && C().lang() === "kk" ? (hint.why_kk || hint.why_ru) : hint.why_ru;
      return h("div", { "class": "bk-banner bc-joint-hint", role: "note" }, [
        h("p", { "class": "bc-joint-hint__title" }, [C().icon ? C().icon("users") : null,
          h("span", {}, t("joint.hint.title", { n: hint.services.length, list: joinNames(hint.services) }))]),
        why ? h("p", { "class": "bc-meta bc-joint-hint__why" }, why) : null,
        h("div", { "class": "bc-joint-hint__actions" }, [
          h("button", { "class": "bk-btn bc-joint-hint__accept", type: "button", onclick: function () {
            setServices(hint.services.map(function (sid, i) { return { service: sid, role: i === 0 ? "lead" : "partner" }; }),
                        t("joint.hint.accepted", { list: joinNames(hint.services) }));
          } }, t("joint.hint.accept")),
          h("button", { "class": "bc-link", type: "button", onclick: function () { jointUi.hintHidden = true; render(); } },
            t("joint.hint.dismiss"))])]);
    }

    // Строка части: значок статуса · служба (ведущая — пометкой) · сегменты «ждёт · в работе · сделано».
    function partRow(part, j) {
      var editable = current.status !== "rejected";
      // Одна служба — статус ведут прежние «Взять в работу» и «Отметить исправленным» (с обязательным «что сделали»,
      // R11 §2.3); сегменты частей — только у совместного исполнения.
      var seg = !j.joint ? null : h("div", { "class": "bk-seg bc-joint__seg", role: "group",
                           "aria-label": t("joint.part.menu", { service: serviceLabel(part.service) }) },
        PART_STATUSES.map(function (st) {
          return h("button", { "class": "bk-seg__btn bc-joint__segbtn", type: "button", "data-status": st,
                               "aria-pressed": part.status === st ? "true" : "false", disabled: editable ? null : true,
                               onclick: function () {
                                 if (part.status === st) return;
                                 if (st === "done") { jointUi.noteFor = part.service; render(); focusNote(); return; }
                                 setPart(part.service, st);
                               } }, t("joint.part." + st));
        }));
      var tools = [];
      if (editable && isOpen() && part.role !== "lead" && j.joint) {
        tools.push(h("button", { "class": "bc-link bc-joint__remove", type: "button",
                                 "aria-label": t("joint.remove", { service: serviceLabel(part.service) }), onclick: function () {
          var rest = j.services.filter(function (p) { return p.service !== part.service; })
            .map(function (p) { return { service: p.service, role: p.role }; });
          setServices(rest);
        } }, t("joint.remove_short")));
      }
      var li = h("li", { "class": "bc-joint__part", "data-service": part.service, "data-status": part.status }, [
        h("div", { "class": "bc-joint__head" }, [partIcon(part.status),
          h("span", { "class": "bc-joint__name" }, serviceLabel(part.service)),
          j.joint ? h("span", { "class": "bk-tag bc-joint__role" }, t("joint.role." + part.role)) : null]),
        part.note ? h("p", { "class": "bc-meta bc-joint__note" }, "«" + part.note + "»") : null,
        seg].concat(tools));
      if (jointUi.noteFor === part.service) {
        var input = h("input", { name: "part_note", maxlength: "120", value: part.note || "", required: true,
                                 "aria-describedby": "bc-part-hint-" + uid });
        var noteError = h("p", { "class": "bc-staff__fix-error", role: "alert", hidden: true });
        li.appendChild(h("form", { "class": "bc-staff__form bc-joint__noteform", onsubmit: function (e) {
          e.preventDefault();
          // «Сделано» — с одной строкой «что сделала служба», как «что сделали» у «Отметить исправленным» (R11 §2.3):
          // жители видят «Водоканал — сделано: Трубу заменили», а не пустое «сделано».
          if (input.value.trim().length < 3) { noteError.textContent = t("staff.fixed.need_what"); noteError.hidden = false; input.focus(); return; }
          setPart(part.service, "done", input.value.trim());
        } }, [field(t("joint.part.note"), input, t("joint.part.note_hint"), "bc-part-hint-" + uid), noteError,
              h("div", { "class": "bc-joint__formrow" }, [
                h("button", { "class": "bk-btn", type: "submit" }, t("common.action.save")),
                h("button", { "class": "bc-link", type: "button", onclick: function () { jointUi.noteFor = null; render(); } },
                  t("common.action.cancel"))])]));
      }
      return li;
    }
    function focusNote() { var f = root.querySelector("[name=part_note]"); if (f) f.focus(); }

    function serviceSelect(name, exclude, label) {
      var select = h("select", { name: name, required: true }, [h("option", { value: "" }, label)]);
      services().forEach(function (s) {
        if (exclude.indexOf(s.id) >= 0) return;
        select.appendChild(h("option", { value: s.id }, serviceLabel(s.id, s.ru)));
      });
      return select;
    }

    // «Передать в другую службу»: кому (подсказка R04 — первой), причина — чипы и строка, «оставить участником».
    function handoffForm(j) {
      var now = j.services.map(function (p) { return p.service; });
      var select = serviceSelect("to", [j.lead], t("joint.handoff.need_to"));
      var hint = routeHint();
      if (hint && hint.services) {
        var suggested = hint.services.filter(function (sid) { return sid !== j.lead; })[0];
        if (suggested) select.value = suggested;
      }
      var chosen = { code: null };
      var chips = h("div", { "class": "bk-chips bc-joint__reasons", role: "group", "aria-label": t("joint.handoff.reason") },
        REASONS.map(function (code) {
          return h("button", { "class": "bk-chip", type: "button", "data-reason": code, "aria-pressed": "false",
                               onclick: function (e) {
                                 chosen.code = chosen.code === code ? null : code;
                                 chips.querySelectorAll(".bk-chip").forEach(function (c) {
                                   c.setAttribute("aria-pressed", c.getAttribute("data-reason") === chosen.code ? "true" : "false");
                                 });
                                 e.currentTarget.focus();
                               } }, t("handoff.reason." + code));
        }));
      var text = h("input", { name: "reason", maxlength: "160" });
      var keep = h("input", { type: "checkbox", name: "keep" });
      var error = h("p", { "class": "bc-staff__fix-error", role: "alert", hidden: true });
      var form = h("form", { "class": "bc-staff__form bc-joint__form bc-joint__handoff", onsubmit: function (e) {
        e.preventDefault();
        var fail = function (msg) { error.textContent = msg; error.hidden = false; };
        if (!select.value) { fail(t("joint.handoff.need_to")); select.focus(); return; }
        var reason = text.value.trim();
        if (!chosen.code && reason.length < 3) { fail(t("joint.handoff.need_reason")); text.focus(); return; }
        error.hidden = true;
        var to = select.value;
        call("POST", "/complaints/" + id + "/handoff", { to: to, reason: reason || null, reason_code: chosen.code,
                                                        keep: keep.checked, expected_lead: j.lead })
          .then(function (res) { jointDone(res, t("joint.handoff.done", { service: serviceLabel(to) })); });
      } }, [
        field(t("joint.handoff.to"), select),
        h("p", { "class": "bc-label" }, t("joint.handoff.reason")), chips,
        field(t("joint.handoff.reason_text"), text),
        h("label", { "class": "bc-staff__check" }, [keep, h("span", {}, t("joint.handoff.keep", { service: serviceLabel(j.lead) }))]),
        error,
        h("div", { "class": "bc-joint__formrow" }, [
          h("button", { "class": "bk-btn", type: "submit" }, t("joint.handoff.send")),
          h("button", { "class": "bc-link", type: "button", onclick: function () { jointUi.form = null; render(); } },
            t("common.action.cancel"))])]);
      if (now.length >= 3) keep.disabled = true;   // больше трёх служб на обращение не бывает
      return form;
    }

    function addForm(j) {
      var now = j.services.map(function (p) { return p.service; });
      var select = serviceSelect("service", now, t("joint.add.service"));
      return h("form", { "class": "bc-staff__form bc-joint__form bc-joint__add", onsubmit: function (e) {
        e.preventDefault();
        if (!select.value) { select.focus(); return; }
        var sid = select.value;
        var list = j.services.map(function (p) { return { service: p.service, role: p.role }; })
          .concat([{ service: sid, role: "partner" }]);
        setServices(list, t("joint.add.done", { service: serviceLabel(sid) }));
      } }, [field(t("joint.add.service"), select),
            h("div", { "class": "bc-joint__formrow" }, [
              h("button", { "class": "bk-btn", type: "submit" }, t("joint.add.send")),
              h("button", { "class": "bc-link", type: "button", onclick: function () { jointUi.form = null; render(); } },
                t("common.action.cancel"))])]);
    }

    // Передачи — свёрнуты: когда, откуда → куда, причина и роль (не имя) сотрудника.
    function handoffHistory(j) {
      if (!j.handoffs || !j.handoffs.length) return null;
      var more = h("details", { "class": "bk-details bc-joint__history" },
        [h("summary", {}, t("joint.history.title") + " · " + j.handoffs.length)]);
      more.appendChild(h("ol", { "class": "bc-joint__hlist" }, j.handoffs.slice().reverse().map(function (x) {
        return h("li", {}, [
          h("span", { "class": "bc-joint__hroute" }, t("joint.history.item", { from: serviceLabel(x.from, "—"), to: serviceLabel(x.to) })),
          x.reason ? h("span", { "class": "bc-joint__hreason" }, " · «" + x.reason + "»") : null,
          h("span", { "class": "bc-meta" }, " · " + C().formatDate(x.at) + (x.by_role ? " · " + t("joint.by." + x.by_role) : ""))]);
      })));
      return more;
    }

    function jointBlock() {
      var j = jointInfo();
      if (!j || !(j.services || []).length) return null;
      var box = h("section", { "class": "bc-staff__form bc-joint", "aria-label": t("joint.title") }, [
        h("p", { "class": "bc-label" }, t("joint.title"))]);
      var hint = hintBanner(j);
      if (hint) box.appendChild(hint);
      box.appendChild(h("ul", { "class": "bc-joint__parts" }, j.services.map(function (p) { return partRow(p, j); })));
      if (isOpen()) {
        if (jointUi.form === "handoff") box.appendChild(handoffForm(j));
        else if (jointUi.form === "add") box.appendChild(addForm(j));
        else {
          box.appendChild(h("div", { "class": "bc-joint__actions" }, [
            h("button", { "class": "bk-btn bc-joint__open-handoff", type: "button",
                          onclick: function () { jointUi.form = "handoff"; render(); var f = root.querySelector("[name=to]"); if (f) f.focus(); } },
              [C().icon ? C().icon("forward") : null, h("span", {}, t("joint.handoff.open"))]),
            j.services.length < 3 ? h("button", { "class": "bk-btn bc-joint__open-add", type: "button",
                          onclick: function () { jointUi.form = "add"; render(); var f = root.querySelector("[name=service]"); if (f) f.focus(); } },
              [C().icon ? C().icon("plus") : null, h("span", {}, t("joint.add.open"))]) : null]));
        }
      }
      var history = handoffHistory(j);
      if (history) box.appendChild(history);
      return box;
    }

    // Совместная жалоба: «исправлено» — только когда все остальные службы отметили свою часть (правило 1 R09).
    function waitingOthers() {
      var j = jointInfo();
      if (!j || !j.joint) return [];
      return j.services.filter(function (p) { return p.role !== "lead" && p.status !== "done"; }).map(function (p) { return p.service; });
    }

    // «Черновик ответа» (R04 POST /reply-draft): факты — из записи R09 кодом; сотрудник правит перед отправкой.
    function draftReply(area, hintBox) {
      jointUi.draft = "loading";
      hintBox.textContent = t("reply.draft.loading");
      hintBox.hidden = false;
      var lang = C().lang ? C().lang() : "ru";
      return rawCall("/reply-draft", { complaint_id: id, status: current.status, lang: lang }, csrf()).then(function (res) {
        var b = res.ok && res.body;
        // R04 reply_draft: {text, draft_ru, draft_kk, lang, …} — черновик на языке сотрудника.
        var text = b && ((lang === "kk" ? b.draft_kk : b.draft_ru) || b.text || b.draft || b.reply);
        if (!text) { jointUi.draft = "unavailable"; hintBox.textContent = t("reply.draft.unavailable"); return; }
        jointUi.draft = "idle";
        area.value = String(text).slice(0, 320);
        hintBox.textContent = t("reply.draft.hint");
        area.focus();
      });
    }

    function render() {
      root.innerHTML = "";
      if (!current) { root.appendChild(h("p", { "class": "bc-meta" }, t("mine.loading"))); return; }
      var p = current.passport_view || {};
      var r = current.resolution || {};
      var shown = C().displayStatus ? C().displayStatus(current) : current.status;
      // opts.compact (карточка цели R07): статус, число людей и категорию карточка уже показывает — не повторяем.
      if (!opts.compact) {
        root.appendChild(h("p", { "class": "bc-staff__summary" }, [
          h("strong", {}, current.code + " · "), h("span", { "class": "bk-status", "data-status": shown }, t("status." + shown)),
          " · ", t("mine.reporters", { n: current.reporters || 1 })]));
        // Уточнение — вторая строка после категории (UX_SPEC §10), не отдельный бейдж.
        root.appendChild(h("p", { "class": "bc-meta" }, C().categoryLabel(current.category) +
          (current.subtopic ? " · " + C().subtopicLabel(current.category, current.subtopic) : "")));
        // Текст жителя — оригинал, только акимату (staff_view); грубые слова — пометкой (п. 8, R10 B-064).
        // В карточке цели R07 (compact) тексты показывает сама карточка («Что пишут жители»).
        if (current.text) {
          root.appendChild(h("p", { "class": "bc-staff__text" }, [h("span", {}, "«" + current.text + "»"),
            current.moderation && current.moderation.rude ? h("span", { "class": "bk-tag bc-tag--rude" }, t("moderation.rude")) : null]));
        }
      }
      if (p.update_overdue) root.appendChild(h("p", { "class": "bc-overdue" }, t("passport.update_overdue")));
      if (r.state) root.appendChild(h("p", { "class": "bc-meta" }, t("staff.votes", {
        yes: (r.votes || {}).yes || 0, no: (r.votes || {}).no || 0, cant: (r.votes || {}).cant || 0 })));
      var willSee = t("fix.will_see", { n: current.subscribers || current.reporters || 1 });

      // 0) Раунд 15: «Службы» — кто исполняет, подсказка R04, передача и совместное исполнение.
      var jb = jointBlock();
      if (jb) root.appendChild(jb);
      var others = waitingOthers();

      // 1) «Отметить исправленным» → форма «Сообщить жителям об устранении» — главное действие карточки.
      //    opts.fix === false — в карточке цели R07: там своя кнопка «Отметить исправленным» (открывает fixForm).
      //    Совместная жалоба: пока другие службы не отметили свою часть — кнопка недоступна, видно, кого ждём.
      if (opts.fix !== false && isOpen() && !fixing) {
        root.appendChild(h("div", { "class": "bc-staff__form" }, [
          h("button", { "class": "bk-btn bk-btn--primary bk-btn--block bc-staff__open-fix", type: "button",
                        disabled: others.length ? true : null, "aria-describedby": others.length ? "bc-wait-" + uid : null,
                        onclick: function () {
                          fixing = true; render();
                          var what = root.querySelector("[name=what_done]");
                          if (what) what.focus();
                        } }, t("heat.mark_fixed")),
          others.length ? h("p", { "class": "bc-meta bc-joint__waiting", id: "bc-wait-" + uid },
                            t("joint.waiting", { list: joinNames(others) })) : h("p", { "class": "bc-meta" }, willSee)]));
      }
      if (opts.fix !== false && isOpen() && fixing && !others.length) {
        var preview = h("ul", { "class": "bc-thumbs bc-thumbs--small" });
        var input = h("input", { type: "file", accept: "image/jpeg,image/png,image/webp", "class": "bc-photo-input" });
        input.addEventListener("change", function () {
          var file = input.files && input.files[0];
          if (!file) return;
          window.BirgeComplaintPhotos.shrink(file).then(function (shrunk) {
            photo = shrunk;
            preview.innerHTML = "";
            preview.appendChild(h("li", { "class": "bc-thumb" }, [h("img", { src: shrunk.url, alt: "" }),
              h("button", { "class": "bk-iconbtn bc-thumb__remove", type: "button", "aria-label": t("complaint.photo.remove"),
                            onclick: function () { photo = null; preview.innerHTML = ""; } }, "×")]));
            input.value = "";
          }, function () { fixError(input.form || input.parentNode, t("complaint.photo.bad_type")); });
        });
        var fixed = h("form", { "class": "bc-staff__form bc-staff__fix", onsubmit: function (e) { e.preventDefault(); markFixed(fixed); } }, [
          h("p", { "class": "bc-label" }, t("fix.title")),
          field(t("fix.what_done"), h("input", { name: "what_done", maxlength: String(WHAT_DONE_MAX), required: true,
                                                 "aria-describedby": "bc-what-hint-" + uid }), t("staff.fixed.what_hint"), "bc-what-hint-" + uid),
          input,
          h("button", { "class": "bk-btn bc-photo-add", type: "button", onclick: function () { input.click(); } },
            [C().icon ? C().icon("camera") : null, h("span", {}, t("fix.photo"))]),
          preview,
          h("button", { "class": "bk-btn bk-btn--primary bk-btn--block", type: "submit" }, t("fix.send")),
          h("p", { "class": "bc-meta" }, willSee)]);
        root.appendChild(fixed);
      }

      // 2) Паспорт решения: сверху — что есть сейчас, «Изменить» открывает 3 поля (+3 при задержке).
      var passport = h("div", { "class": "bc-staff__form" }, [h("p", { "class": "bc-label" }, t("passport.title")), passportSummary()]);
      if (current.status !== "rejected") {
        if (editing) passport.appendChild(passportForm());
        else passport.appendChild(h("button", { "class": "bk-btn bc-staff__edit", type: "button",
                                                onclick: function () { editing = true; render(); } }, t("passport.edit")));
      }
      root.appendChild(passport);

      // 3) Одно обновление всем «Я тоже» (п. 3): число людей видно до отправки.
      var area = h("textarea", { name: "text", maxlength: "320", rows: "2", required: true, placeholder: t("broadcast.placeholder") });
      var draftNote = h("p", { "class": "bc-meta bc-staff__draft-note", role: "status", hidden: true });
      var draft = jointUi.draft === "unavailable" ? null : h("button", { "class": "bc-link bc-staff__draft", type: "button", hidden: true,
        onclick: function () { draftReply(area, draftNote).then(function () { if (jointUi.draft === "unavailable" && draft) draft.hidden = true; }); } },
        [C().icon ? C().icon("message") : null, h("span", {}, t("reply.draft"))]);
      if (draft) modules().then(function (list) { if (draftReady(list)) draft.hidden = false; });
      var update = h("form", { "class": "bc-staff__form bc-staff__broadcast", onsubmit: function (e) { e.preventDefault(); postUpdate(update); } }, [
        field(t("broadcast.title"), area), draft, draftNote,
        h("button", { "class": "bk-btn bk-btn--block", type: "submit" }, t("broadcast.send")),
        h("p", { "class": "bc-meta" }, willSee)]);
      root.appendChild(update);
      root.appendChild(h("p", { "class": "bc-staff__note", role: "status" }));
      if (lastNote) note(lastNote.text, lastNote.error);
    }

    function refresh() {
      return call("GET", "/complaints/" + encodeURIComponent(id)).then(function (res) {
        // opts.staffOnly (карточка R07): не сотрудник (нет служебных полей) или ошибка — блока просто нет.
        if (res.ok && opts.staffOnly && !(res.data.complaint && "subscribers" in res.data.complaint)) { root.hidden = true; return; }
        if (res.ok) {
          current = res.data.complaint; root.hidden = false; render();
          // Открыли из строки «Обращений» выбором «Сделано» у части — сразу курсор в «что сделала служба».
          if (opts.openPart) { opts.openPart = null; focusNote(); }
        }
        else if (opts.staffOnly) { root.hidden = true; }
        else { root.innerHTML = ""; root.appendChild(h("p", { "class": "bk-error" }, t("mine.error.title"))); }
      });
    }

    // Смена языка (в том числе после асинхронной загрузки словаря R11) — перерисовать подписи; открытая правка
    // паспорта закрывается без потери сохранённого (несохранённые поля — как после «Отмена»).
    function onLang() {
      // Карточку R07 перерисовывают целиком: снятый со страницы блок отписывается сам (без утечки слушателей).
      if (!root.isConnected) { window.removeEventListener("birge:lang", onLang); return; }
      if (current) render();
    }
    window.addEventListener("birge:lang", onLang);
    render();
    refresh();
    return { refresh: refresh, destroy: function () {
      window.removeEventListener("birge:lang", onLang);
      if (root.parentNode) root.parentNode.removeChild(root);
    } };
  }

  // ---------------------------------------------------------------- форма для карточки цели R07
  // «Отметить исправленным» в карточке цели R07 (R11 разбор 9 №1, IA_WAVE2 §2.3): та же одна строка «что сделали»
  // и фото «после», но для всех открытых обращений цели (R07 отмечает исправленными все open_ids).
  //   BirgeComplaintStaff.fixForm(container, { complaintIds, csrf, onDone(results), onCancel() }) -> { destroy() }
  function fixForm(container, opts) {
    opts = opts || {};
    var ids = (opts.complaintIds || []).filter(Boolean);
    var csrf = function () {
      if (typeof opts.csrf === "function") return opts.csrf() || "";
      if (opts.csrf) return opts.csrf;
      var shell = window.CivicShell;
      return shell && typeof shell.csrfToken === "function" ? (shell.csrfToken() || "") : "";
    };
    var photo = null;
    function post(path, body) {
      return fetch(API + path, { method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "Accept": "application/json", "X-CSRF-Token": csrf() },
        body: JSON.stringify(body) }).then(function (r) {
          return r.json().catch(function () { return null; }).then(function (j) {
            if (!r.ok || !j || j.ok === false) { var e = new Error("HTTP " + r.status); e.status = r.status; e.body = j; throw e; }
            return j.data;
          });
        });
    }
    var hintId = "bc-fixform-hint-" + Math.random().toString(36).slice(2, 8);
    var what = h("input", { name: "what_done", maxlength: "120", required: true, "aria-describedby": hintId });
    var preview = h("ul", { "class": "bc-thumbs bc-thumbs--small" });
    var input = h("input", { type: "file", accept: "image/jpeg,image/png,image/webp", "class": "bc-photo-input" });
    var error = h("p", { "class": "bc-staff__fix-error", role: "alert", hidden: true });
    var send = h("button", { "class": "bk-btn bk-btn--primary bk-btn--block", type: "submit" }, t("fix.send"));
    // «Увидят N человек» до действия (R11 §2.3): автор и «Я тоже» всех открытых обращений цели.
    var willSee = h("p", { "class": "bc-meta bc-fixform__will-see", hidden: true });
    Promise.all(ids.map(function (cid) {
      return fetch(API + "/complaints/" + encodeURIComponent(cid), { credentials: "same-origin", headers: { "Accept": "application/json" } })
        .then(function (r) { return r.ok ? r.json() : null; }).then(function (j) {
          var c = j && j.data && j.data.complaint;
          return c && typeof c.subscribers === "number" ? c.subscribers : 0;
        }, function () { return 0; });
    })).then(function (counts) {
      var n = counts.reduce(function (a, b) { return a + b; }, 0);
      if (n > 0) { willSee.textContent = t("fix.will_see", { n: n }); willSee.hidden = false; }
    });
    var form = h("form", { "class": "bc-staff bc-staff__form bc-staff__fix bc-fixform" }, [
      h("p", { "class": "bc-label" }, t("fix.title")),
      h("label", { "class": "bc-staff__field" }, [h("span", { "class": "bc-label" }, t("fix.what_done")), what,
        h("span", { "class": "bc-meta bc-staff__hint", id: hintId }, t("staff.fixed.what_hint"))]),
      input,
      h("button", { "class": "bk-btn bc-photo-add", type: "button", onclick: function () { input.click(); } },
            [C().icon ? C().icon("camera") : null, h("span", {}, t("fix.photo"))]),
      preview, error, send, willSee,
      h("button", { "class": "bc-link", type: "button", onclick: function () { destroy(); if (opts.onCancel) opts.onCancel(); } },
        t("common.action.cancel"))]);
    function fail(text) { error.textContent = text; error.hidden = false; send.disabled = false; }
    input.addEventListener("change", function () {
      var file = input.files && input.files[0];
      if (!file) return;
      window.BirgeComplaintPhotos.shrink(file).then(function (shrunk) {
        photo = shrunk;
        preview.innerHTML = "";
        preview.appendChild(h("li", { "class": "bc-thumb" }, [h("img", { src: shrunk.url, alt: "" }),
          h("button", { "class": "bk-iconbtn bc-thumb__remove", type: "button", "aria-label": t("complaint.photo.remove"),
                        onclick: function () { photo = null; preview.innerHTML = ""; } }, "×")]));
        input.value = "";
      }, function () { fail(t("complaint.photo.bad_type")); });
    });
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var text = what.value.trim();
      if (text.length < 3) { fail(t("staff.fixed.need_what")); return; }
      send.disabled = true; error.hidden = true;
      var results = [];
      // По очереди: фото «после» каждому обращению цели (его жители проверяют своё), затем «исправлено».
      ids.reduce(function (chain, id) {
        return chain.then(function () {
          var up = photo ? window.BirgeComplaintPhotos.upload(id, photo.blob, "after", csrf())
            .then(null, function () { throw { photo: true }; }) : Promise.resolve(null);
          return up.then(function (uploaded) {
            return post("/complaints/" + encodeURIComponent(id) + "/status",
                        { status: "fixed", what_done: text, photos: uploaded ? [uploaded.id] : [] });
          }).then(function (data) { results.push(data); });
        });
      }, Promise.resolve()).then(function () {
        destroy();
        if (opts.onDone) opts.onDone(results);
      }, function (err) {
        fail(t(err && err.photo ? "staff.photo.failed" : "complaint.error.send"));
      });
    });
    function destroy() { if (form.parentNode) form.parentNode.removeChild(form); }
    container.appendChild(form);
    what.focus();
    return { destroy: destroy };
  }

  window.BirgeComplaintStaff = { mount: mount, fixForm: fixForm };
})();
