/* R08 · стенд today.html: язык и монтирование сводки (отдельным файлом — CSP без встроенных скриптов). */
(function () {
  "use strict";
  var seg = document.querySelectorAll("[data-lang]");
  function sync(lang) {
    seg.forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.getAttribute("data-lang") === lang));
    });
  }
  seg.forEach(function (b) {
    b.addEventListener("click", function () {
      window.BirgeI18n.setLang(b.getAttribute("data-lang"));
    });
  });
  window.BirgeI18n.onChange(sync);
  window.BirgeI18n.ready.then(sync);
  window.__today = window.BirgeToday.mount(document.getElementById("today"), { apiBase: "/api/civic/v2" });
})();
