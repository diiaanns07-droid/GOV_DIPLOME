// R15 · обвязка браузерной пробы раунда 15: грузит экран роли и монтирует его в #r15-root, как оболочка R01.
// ?m=agencies|meetings|analyst|works-calendar|together · &role=akimat|resident · &lang=ru|kk · &hash=<глубокая ссылка>
// · &view=yard|initiatives (R16) · m=intake&fake=1 — «ИИ-разбор пачки» R04 (П3) с подложным api.v2: нагрузка во ВСЕХ полях
// ответа разбора, примера и commit (контракт INTEGRATION R04 п. 9.1) — экран должен вывести её текстом.
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
    notify: { css: ["/civic/notify/notify.css"], js: ["/civic/notify/notify.js"], global: "BirgeNotify" },
    intake: { css: ["/civic/intake/intake.css"], js: ["/civic/intake/intake.js"], global: "BirgeIntake" }
  };
  // П3: подложный клиент шлюза для экрана R04 (как BirgeShell.api.v2: Promise с телом JSON). Нагрузка — в каждом поле.
  var P = function (tag) { return "<img src=x data-r15x=" + tag + " onerror=__r15x()>R15X"; };
  var FAKE_API = { calls: [], v2: function (method, path, body) {
    FAKE_API.calls.push(method + " " + path);
    var task = function (n, placed) {
      return { id: "t-" + n, title_ru: P("title" + n) + " фонарь", title_kk: P("titlekk" + n), category: "lighting",
        subtopic: P("sub" + n), services: [{ id: "akimat", role: "lead", name_ru: P("svc" + n) + " служба", name_kk: P("svckk" + n) }],
        joint: n === 1, why_ru: P("why" + n) + " почему", why_kk: P("whykk" + n),
        target: placed ? { kind: "yard", id: "yard-1026285032", label_ru: P("target" + n) + " двор", label_kk: P("targetkk" + n) } : null,
        point: placed ? [71.404739, 51.1111745] : null, address_text: P("addr" + n) + " адрес", text_ids: ["r15-" + n],
        people: 3, urgent: n === 1, urgent_why_ru: P("urgent" + n) + " срочно", urgent_why_kk: P("urgentkk" + n) };
    };
    var reply;
    if (/intake\/sample/.test(path)) {
      reply = { name: "night", texts: [{ id: "r15-1", text: P("sample") + " текст" }], demo: true, source: P("source") };
    } else if (/intake\/commit/.test(path)) {
      reply = { batch_id: "b-r15fake0001", created: 1, existing: 0, skipped_no_address: 1, demo: true,
        records: [{ task_id: "t-1", complaint_id: "c-000000000001", code: P("code") }] };
    } else if (/intake\/analyze/.test(path)) {
      reply = { batch_id: "b-r15fake0001", method: P("method"), demo: true, version: P("version"),
        summary: { total: 3, tasks: 2, services: 1, urgent: 1, merged: 1, no_address: 1, ms: 12 },
        tasks: [task(1, true), task(2, false)] };
    } else {
      return Promise.reject(Object.assign(new Error("R15: нет в подложке"), { status: 404 }));
    }
    return new Promise(function (ok) { setTimeout(function () { ok(JSON.parse(JSON.stringify(reply))); }, 50); });
  } };
  window.__r15fake = FAKE_API;
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
      var opts = {
        apiBase: "/api/civic/v2", role: role, mode: role, lang: lang, embedded: false, view: q.get("view") || undefined
      };
      if (q.get("fake") === "1") opts.api = FAKE_API;
      window.__r15handle = mod.mount(document.getElementById("r15-root"), opts);
      window.__r15ready = true;
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
