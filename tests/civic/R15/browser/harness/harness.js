// R15 · обвязка браузерной пробы раунда 15: грузит экран роли и монтирует его в #r15-root, как оболочка R01.
// ?m=agencies|meetings|analyst|works-calendar|together · &role=akimat|resident · &lang=ru|kk · &hash=<глубокая ссылка>
// · &view=yard|initiatives (R16).
// CSRF-токен сотрудника кладёт проба (sessionStorage r15csrf) — экраны берут его через CivicShell.csrfToken().
(function () {
  "use strict";
  var q = new URLSearchParams(location.search);
  var name = q.get("m") || "", role = q.get("role") || "akimat", lang = q.get("lang") || "ru";
  var token = null;
  try { token = sessionStorage.getItem("r15csrf"); } catch (e) { token = null; }
  window.CivicShell = { csrfToken: function () { return role === "akimat" ? token : null; } };
  window.__r15csp = window.__r15csp || [];
  document.addEventListener("securitypolicyviolation", function (e) {
    window.__r15csp.push(e.violatedDirective + " " + (e.blockedURI || ""));
  });
  if (q.get("hash")) history.replaceState(null, "", location.pathname + location.search + "#" + q.get("hash"));
  var MODULES = {
    agencies: { css: ["/civic/agencies/agencies.css"], js: ["/civic/agencies/crisis-layer.js", "/civic/agencies/agencies.js"],
      global: "BirgeAgencies" },
    meetings: { css: ["/civic/qa/qa.css", "/civic/meetings/meetings.css"], js: ["/civic/qa/qa.js", "/civic/meetings/meetings.js"],
      global: "BirgeMeetings" },
    analyst: { css: ["/civic/assistant/analyst.css"], js: ["/civic/assistant/analyst.js"], global: "BirgeAnalyst" },
    "works-calendar": { css: ["/civic/works-calendar/works-calendar.css"], js: ["/civic/works-calendar/works-calendar.js"],
      global: "BirgeWorksCalendar" },
    together: { css: ["/civic/together/together.css"],
      js: ["/civic/together/together-text.js", "/civic/together/together.js"], global: "BirgeTogether" },
    notify: { css: ["/civic/notify/notify.css"], js: ["/civic/notify/notify.js"], global: "BirgeNotify" }
  };
  var spec = MODULES[name];
  function load(list, i, done) {
    if (i >= list.length) { done(); return; }
    var s = document.createElement("script");
    s.src = list[i];
    s.onload = function () { load(list, i + 1, done); };
    s.onerror = function () { window.__r15missing = (window.__r15missing || []).concat(list[i]); load(list, i + 1, done); };
    document.head.appendChild(s);
  }
  function start() {
    if (!spec) { window.__r15ready = "unknown module"; return; }
    spec.css.forEach(function (href) {
      var l = document.createElement("link"); l.rel = "stylesheet"; l.href = href; document.head.appendChild(l);
    });
    load(spec.js, 0, function () {
      var mod = window[spec.global];
      if (!mod || typeof mod.mount !== "function") { window.__r15ready = "no " + spec.global; return; }
      try {
        if (window.BirgeI18n && typeof window.BirgeI18n.setLang === "function") window.BirgeI18n.setLang(lang);
      } catch (e) { /* словарь R11 — по желанию */ }
      window.__r15handle = mod.mount(document.getElementById("r15-root"), {
        apiBase: "/api/civic/v2", role: role, mode: role, lang: lang, embedded: false, view: q.get("view") || undefined
      });
      window.__r15ready = true;
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
