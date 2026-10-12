/* FIXTURE harness R06: монтирует CivicFeedback и mountModeration на стенде. */
(function () {
  "use strict";
  var csrf = null;
  var api = window.CivicFeedback.createFetchApi("/api/civic/v1", { csrfToken: function () { return csrf; } });
  var resident = null;
  var moderation = null;
  var target = document.getElementById("target");

  function post(path, body) {
    return fetch(path, {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}),
    }).then(function (r) { return r.json(); });
  }

  function showSession(data) {
    csrf = data.csrf_token;
    document.getElementById("session").textContent = data.authenticated ? data.user.name + " (" + data.user.role + ")" : "не вошли";
  }

  function mountResident() {
    if (resident) resident.destroy();
    var value = target.value.split(":");
    var options = { root: document.getElementById("resident-root"), api: api };
    if (value[0] === "object") options.objectId = value[1];
    else options.geometry = { type: "Point", coordinates: value[1].split(",").map(Number) };
    resident = window.CivicFeedback.mount(options);
    window.__r06 = window.__r06 || {};
    window.__r06.resident = resident;
  }

  function mountModeration() {
    if (moderation) moderation.destroy();
    moderation = window.CivicFeedback.mountModeration({ root: document.getElementById("moderation-root"), api: api });
    window.__r06 = window.__r06 || {};
    window.__r06.moderation = moderation;
  }

  // Ссылка из квитанции (#civic-receipt=…) открывает панель статуса — так R01 может сделать в shell.js.
  var receiptPanel = null;
  function mountReceiptPanel(receiptId) {
    if (receiptPanel) receiptPanel.destroy();
    receiptPanel = window.CivicFeedback.mountReceipt({ root: document.getElementById("receipt-root"), api: api,
      receiptId: receiptId || null });
    window.__r06 = window.__r06 || {};
    window.__r06.receipt = receiptPanel;
  }

  function login(role) {
    post("/harness/login", { role: role }).then(function (r) { showSession(r.data); mountModeration(); });
  }

  document.getElementById("login-editor").addEventListener("click", function () { login("editor"); });
  document.getElementById("login-resident").addEventListener("click", function () { login("resident"); });
  // Выход не перемонтирует очередь: проверяем, что открытая форма не сработает после logout.
  // Выход очищает черновики и номера квитанций этой вкладки (CivicFeedback.clearDrafts).
  document.getElementById("logout").addEventListener("click", function () {
    post("/harness/logout").then(function (r) {
      showSession(r.data);
      window.CivicFeedback.clearDrafts();
      mountResident();
    });
  });
  document.getElementById("check-receipt").addEventListener("click", function () { mountReceiptPanel(null); });
  window.addEventListener("hashchange", function () {
    var id = window.CivicFeedback.receiptFromLocation();
    if (id) mountReceiptPanel(id);
  });
  document.getElementById("expire").addEventListener("click", function () { post("/harness/expire"); });
  target.addEventListener("change", mountResident);

  fetch("/harness/session", { credentials: "same-origin" }).then(function (r) { return r.json(); }).then(function (r) {
    showSession(r.data);
    mountResident();
    mountModeration();
    if (window.CivicFeedback.receiptFromLocation()) mountReceiptPanel(null);
    document.body.setAttribute("data-r06-ready", "1");
  });
})();
