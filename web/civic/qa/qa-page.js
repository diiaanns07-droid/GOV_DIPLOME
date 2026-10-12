/* Birge · «Вопрос акиму» (R13): запуск отдельной страницы web/civic/qa/index.html (без встроенных скриптов — CSP). */
(function () {
  "use strict";
  var I = window.BirgeI18n;
  var role = /[?&]role=akimat(&|$)/.test(location.search) ? "akimat" : "resident";
  var seg = document.querySelectorAll("[data-lang]");
  function syncLang(lang) {
    seg.forEach(function (b) { b.setAttribute("aria-pressed", String(b.getAttribute("data-lang") === lang)); });
    document.title = I.t(role === "akimat" ? "shell.nav.questions_staff" : "common.nav.ask") + " · Birge";
  }
  seg.forEach(function (b) {
    b.addEventListener("click", function () { I.setLang(b.getAttribute("data-lang")); });
  });
  if (I) {
    I.onChange(syncLang);
    I.ready.then(function () { syncLang(I.getLang()); I.apply(document.body); });
  }
  window.BirgeAsk.mount(document.getElementById("qa-page"), { role: role, titleTag: "h1" });
})();
