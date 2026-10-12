/*
 * R09 · волна 2 · Действия сотрудника по одной жалобе (R11 IA_WAVE2 §2.3–2.4). Встраивают R07 в карточку цели,
 * R09 в «Обращения» акимата (complaint-list.js). Новых слоёв карты нет: компонент живёт в карточке.
 *   «Сообщить жителям об устранении» — одна строка «что сделали» (обязательно) + 1 фото «после» (п. 1);
 *   паспорт решения — «Изменить» → 3 поля: кто отвечает, следующий шаг, ориентир устранения; при просрочке —
 *   ещё причина, временная мера, следующее обновление (п. 2);
 *   «Обновление для всех» — одно сообщение автору и всем «Я тоже» (п. 3). Перед действием — «Увидят N человек».
 *
 *   BirgeComplaintStaff.mount(container, { complaintId, csrf: "<токен R02>" | () => токен, onChange(complaint) })
 *     -> { refresh(), destroy() }
 * Тексты — словарь R11 (fix.*, passport.*, broadcast.*, service.*), запасной — complaint-strings.js.
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

  function mount(container, opts) {
    opts = opts || {};
    var id = opts.complaintId;
    var csrf = function () { return typeof opts.csrf === "function" ? opts.csrf() : (opts.csrf || ""); };
    var root = h("section", { "class": "bc-staff", "aria-label": t("staff.title") });
    container.appendChild(root);
    var current = null;
    var photo = null;
    var editing = false;
    var fixing = false;    // R11 §2.3: «Отметить исправленным» открывает форму в той же карточке (не модальное окно)
    var lastNote = null;

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

    function markFixed(form) {
      var what = form.querySelector("[name=what_done]").value.trim();
      if (what.length < 3) { note(t("staff.fixed.need_what"), true); return; }
      var button = form.querySelector("button[type=submit]");
      button.disabled = true;
      // B-056 / R15: сам Blob из shrink(), без fetch(blob:…) — строгая CSP сборки (connect-src без blob:) его запрещает.
      var upload = photo
        ? window.BirgeComplaintPhotos.upload(id, photo.blob, "after", csrf())
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
          photo = null;
        }
        done(res);
      }, function () { button.disabled = false; note(t("complaint.error.send"), true); });
    }

    function savePassport(form) {
      var get = function (name) { var f = form.querySelector("[name=" + name + "]"); return f ? f.value.trim() : undefined; };
      var body = { service: get("service"), next_step: get("next_step"), fix_eta: get("fix_eta") };
      if (form.querySelector("[name=delay_reason]")) {
        body.delay_reason = get("delay_reason"); body.temp_measure = get("temp_measure"); body.next_update_at = get("next_update_at");
      }
      call("POST", "/complaints/" + id + "/passport", body).then(done);
    }

    function postUpdate(form) {
      var text = form.querySelector("[name=text]").value.trim();
      call("POST", "/complaints/" + id + "/update", { text: text }).then(function (res) {
        if (done(res)) form.reset();
      });
    }

    function field(label, input) {
      return h("label", { "class": "bc-staff__field" }, [h("span", { "class": "bc-label" }, label), input]);
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
      }
      var form = h("form", { "class": "bc-staff__form bc-staff__passport-form",
                             onsubmit: function (e) { e.preventDefault(); savePassport(form); } },
        fields.concat([h("button", { "class": "bk-btn bk-btn--block", type: "submit" }, t("common.action.save"))]));
      return form;
    }

    function render() {
      root.innerHTML = "";
      if (!current) { root.appendChild(h("p", { "class": "bc-meta" }, t("mine.loading"))); return; }
      var p = current.passport_view || {};
      var r = current.resolution || {};
      var shown = C().displayStatus ? C().displayStatus(current) : current.status;
      root.appendChild(h("p", { "class": "bc-staff__summary" }, [
        h("strong", {}, current.code + " · "), h("span", { "class": "bk-status", "data-status": shown }, t("status." + shown)),
        " · ", t("mine.reporters", { n: current.reporters || 1 })]));
      // Уточнение — вторая строка после категории (UX_SPEC §10), не отдельный бейдж.
      root.appendChild(h("p", { "class": "bc-meta" }, C().categoryLabel(current.category) +
        (current.subtopic ? " · " + C().subtopicLabel(current.category, current.subtopic) : "")));
      if (p.update_overdue) root.appendChild(h("p", { "class": "bc-overdue" }, t("passport.update_overdue")));
      if (r.state) root.appendChild(h("p", { "class": "bc-meta" }, t("staff.votes", {
        yes: (r.votes || {}).yes || 0, no: (r.votes || {}).no || 0, cant: (r.votes || {}).cant || 0 })));
      var willSee = t("fix.will_see", { n: current.subscribers || current.reporters || 1 });

      // 1) «Отметить исправленным» → форма «Сообщить жителям об устранении» — главное действие карточки.
      if (isOpen() && !fixing) {
        root.appendChild(h("div", { "class": "bc-staff__form" }, [
          h("button", { "class": "bk-btn bk-btn--primary bk-btn--block bc-staff__open-fix", type: "button",
                        onclick: function () {
                          fixing = true; render();
                          var what = root.querySelector("[name=what_done]");
                          if (what) what.focus();
                        } }, t("heat.mark_fixed")),
          h("p", { "class": "bc-meta" }, willSee)]));
      }
      if (isOpen() && fixing) {
        var preview = h("ul", { "class": "bc-thumbs bc-thumbs--small" });
        var input = h("input", { type: "file", accept: "image/jpeg,image/png,image/webp", "class": "bc-photo-input" });
        input.addEventListener("change", function () {
          var file = input.files && input.files[0];
          if (!file) return;
          window.BirgeComplaintPhotos.shrink(file).then(function (shrunk) {
            photo = shrunk;
            preview.innerHTML = "";
            preview.appendChild(h("li", { "class": "bc-thumb" }, h("img", { src: shrunk.url, alt: "" })));
          }, function () { note(t("complaint.photo.bad_type"), true); });
        });
        var fixed = h("form", { "class": "bc-staff__form bc-staff__fix", onsubmit: function (e) { e.preventDefault(); markFixed(fixed); } }, [
          h("p", { "class": "bc-label" }, t("fix.title")),
          field(t("fix.what_done"), h("input", { name: "what_done", maxlength: String(WHAT_DONE_MAX), required: true,
                                                 placeholder: t("staff.fixed.what_hint") })),
          input,
          h("button", { "class": "bk-btn", type: "button", onclick: function () { input.click(); } }, t("fix.photo")),
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
      var update = h("form", { "class": "bc-staff__form bc-staff__broadcast", onsubmit: function (e) { e.preventDefault(); postUpdate(update); } }, [
        field(t("broadcast.title"), h("input", { name: "text", maxlength: "320", required: true, placeholder: t("broadcast.placeholder") })),
        h("button", { "class": "bk-btn bk-btn--block", type: "submit" }, t("broadcast.send")),
        h("p", { "class": "bc-meta" }, willSee)]);
      root.appendChild(update);
      root.appendChild(h("p", { "class": "bc-staff__note", role: "status" }));
      if (lastNote) note(lastNote.text, lastNote.error);
    }

    function refresh() {
      return call("GET", "/complaints/" + encodeURIComponent(id)).then(function (res) {
        if (res.ok) { current = res.data.complaint; render(); }
        else { root.innerHTML = ""; root.appendChild(h("p", { "class": "bk-error" }, t("mine.error.title"))); }
      });
    }

    // Смена языка (в том числе после асинхронной загрузки словаря R11) — перерисовать подписи; открытая правка
    // паспорта закрывается без потери сохранённого (несохранённые поля — как после «Отмена»).
    function onLang() { if (current) render(); }
    window.addEventListener("birge:lang", onLang);
    render();
    refresh();
    return { refresh: refresh, destroy: function () {
      window.removeEventListener("birge:lang", onLang);
      if (root.parentNode) root.parentNode.removeChild(root);
    } };
  }

  window.BirgeComplaintStaff = { mount: mount };
})();
