/*
 * R09 · волна 2 · Действия сотрудника по одной жалобе (встраивает R07 в карточку цели или R01 в «Обращения»):
 *   «Отметить исправленным» = «Служба сообщила об устранении» — одна строка «что сделали» + фото «после» (п. 1);
 *   паспорт решения — 3 поля: следующий шаг, ориентир устранения, причина задержки (+ по желанию мера и дата, п. 2);
 *   «Сообщить всем» — одно обновление автору и всем «Я тоже» (п. 3).
 *
 *   BirgeComplaintStaff.mount(container, { complaintId, csrf: "<токен R02>" | () => токен, onChange(complaint) })
 *     -> { refresh(), destroy() }
 * Тексты — complaint-strings.js (staff.*) или словарь R11. Новых слоёв карты нет: компонент живёт в карточке.
 */
(function () {
  "use strict";
  var API = "/api/civic/v2";
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

  function mount(container, opts) {
    opts = opts || {};
    var id = opts.complaintId;
    var csrf = function () { return typeof opts.csrf === "function" ? opts.csrf() : (opts.csrf || ""); };
    var root = h("section", { "class": "bc-staff", "aria-label": t("staff.title") });
    container.appendChild(root);
    var current = null;
    var photo = null;

    function call(method, path, body) {
      return fetch(API + path, { method: method, credentials: "same-origin",
        headers: { "Content-Type": "application/json", "Accept": "application/json", "X-CSRF-Token": csrf() },
        body: body === undefined ? undefined : JSON.stringify(body) })
        .then(function (r) { return r.json().catch(function () { return null; }).then(function (j) {
          return { ok: r.ok && j && j.ok !== false, status: r.status, data: j && j.data, error: j && j.error };
        }); }, function () { return { ok: false, status: 0 }; });
    }

    function note(text, isError) {
      var box = root.querySelector(".bc-staff__note");
      if (!box) return;
      box.textContent = text;
      box.setAttribute("role", isError ? "alert" : "status");
      box.className = "bc-staff__note" + (isError ? " bc-staff__note--error" : "");
    }

    function done(res, message) {
      if (!res.ok) { note((res.error && res.error.message) || t("complaint.error.send"), true); return false; }
      current = res.data.complaint;
      note(message);
      if (typeof opts.onChange === "function") opts.onChange(current);
      render();
      note(message);
      return true;
    }

    function markFixed(form) {
      var what = form.querySelector("[name=what_done]").value.trim();
      if (what.length < 3) { note(t("staff.fixed.need_what"), true); return; }
      var button = form.querySelector("button[type=submit]");
      button.disabled = true;
      var upload = photo
        ? fetch(photo.url).then(function (r) { return r.blob(); }).then(function (blob) {
            return window.BirgeComplaintPhotos.upload(id, blob, "after", csrf());
          })
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
        if (res && res.ok) photo = null;
        done(res, t("staff.notified", { n: res && res.data ? res.data.notified : 0 }));
      }, function () { button.disabled = false; note(t("complaint.error.send"), true); });
    }

    function savePassport(form) {
      var get = function (name) { return form.querySelector("[name=" + name + "]").value.trim(); };
      call("POST", "/complaints/" + id + "/passport", {
        next_step: get("next_step"), fix_eta: get("fix_eta"), delay_reason: get("delay_reason"),
        temp_measure: get("temp_measure"), next_update_at: get("next_update_at")
      }).then(function (res) { done(res, t("staff.notified", { n: res.data ? res.data.notified : 0 })); });
    }

    function postUpdate(form) {
      var text = form.querySelector("[name=text]").value.trim();
      call("POST", "/complaints/" + id + "/update", { text: text }).then(function (res) {
        if (done(res, t("staff.notified", { n: res.data ? res.data.notified : 0 }))) form.reset();
      });
    }

    function field(label, input) {
      return h("label", { "class": "bc-staff__field" }, [h("span", { "class": "bc-label" }, label), input]);
    }

    function render() {
      root.innerHTML = "";
      if (!current) { root.appendChild(h("p", { "class": "bc-meta" }, t("mine.loading"))); return; }
      var p = current.passport || {};
      var delay = p.delay || {};
      var r = current.resolution || {};
      root.appendChild(h("p", { "class": "bc-staff__summary" }, [
        h("strong", {}, current.code + " · "), t("status." + current.status),
        " · ", t("mine.reporters", { n: current.reporters || 1 })]));
      if (current.passport_view && current.passport_view.update_overdue) {
        root.appendChild(h("p", { "class": "bc-overdue" }, t("staff.update_overdue")));
      }
      if (r.state) root.appendChild(h("p", { "class": "bc-meta" }, t("staff.votes", {
        yes: (r.votes || {}).yes || 0, no: (r.votes || {}).no || 0, cant: (r.votes || {}).cant || 0 })));

      // 1) «Отметить исправленным» — главное действие карточки.
      if (current.status !== "fixed" && current.status !== "rejected") {
        var preview = h("ul", { "class": "bc-thumbs bc-thumbs--small" });
        var input = h("input", { type: "file", accept: "image/jpeg,image/png,image/webp", "class": "bc-photo-input" });
        input.addEventListener("change", function () {
          var file = input.files && input.files[0];
          if (!file) return;
          window.BirgeComplaintPhotos.shrink(file).then(function (shrunk) {
            photo = shrunk;
            preview.innerHTML = "";
            preview.appendChild(h("li", { "class": "bc-thumb" }, h("img", { src: shrunk.url, alt: "" })));
          }, function () { note(t("complaint.photo.bad"), true); });
        });
        var fixed = h("form", { "class": "bc-staff__form", onsubmit: function (e) { e.preventDefault(); markFixed(fixed); } }, [
          h("p", { "class": "bc-label" }, t("staff.fixed.title")),
          field(t("staff.fixed.what"), h("input", { name: "what_done", maxlength: "200", required: true,
                                                     placeholder: t("staff.fixed.what_hint") })),
          input,
          h("button", { "class": "bk-btn", type: "button", onclick: function () { input.click(); } }, t("staff.fixed.photo")),
          preview,
          h("button", { "class": "bk-btn bk-btn--primary bk-btn--block", type: "submit" }, t("staff.fixed.submit"))]);
        root.appendChild(fixed);
      }

      // 2) Паспорт решения: 3 поля сразу, мера и дата обновления — по желанию.
      var passport = h("form", { "class": "bc-staff__form", onsubmit: function (e) { e.preventDefault(); savePassport(passport); } }, [
        h("p", { "class": "bc-label" }, t("staff.passport.title")),
        field(t("staff.passport.next_step"), h("input", { name: "next_step", maxlength: "160", value: p.next_step || "" })),
        field(t("staff.passport.fix_eta"), h("input", { name: "fix_eta", type: "date", value: p.fix_eta || "" })),
        field(t("staff.passport.delay_reason"), h("input", { name: "delay_reason", maxlength: "160", value: delay.reason || "" })),
        h("details", {}, [h("summary", {}, t("mine.details")),
          field(t("staff.passport.temp_measure"), h("input", { name: "temp_measure", maxlength: "160", value: delay.temp_measure || "" })),
          field(t("staff.passport.next_update"), h("input", { name: "next_update_at", type: "date", value: delay.next_update_at || "" }))]),
        h("button", { "class": "bk-btn bk-btn--block", type: "submit" }, t("staff.passport.save"))]);
      root.appendChild(passport);

      // 3) Одно обновление всем «Я тоже».
      var update = h("form", { "class": "bc-staff__form", onsubmit: function (e) { e.preventDefault(); postUpdate(update); } }, [
        field(t("staff.update.title"), h("input", { name: "text", maxlength: "320", required: true })),
        h("button", { "class": "bk-btn bk-btn--block", type: "submit" }, t("staff.update.send", { n: current.reporters || 1 }))]);
      root.appendChild(update);
      root.appendChild(h("p", { "class": "bc-staff__note", role: "status" }));
    }

    function refresh() {
      return call("GET", "/complaints/" + encodeURIComponent(id)).then(function (res) {
        if (res.ok) { current = res.data.complaint; render(); }
        else { root.innerHTML = ""; root.appendChild(h("p", { "class": "bk-error" }, t("mine.error.title"))); }
      });
    }

    render();
    refresh();
    return { refresh: refresh, destroy: function () { if (root.parentNode) root.parentNode.removeChild(root); } };
  }

  window.BirgeComplaintStaff = { mount: mount };
})();
