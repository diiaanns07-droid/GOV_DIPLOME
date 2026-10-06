/* R01 minimal fallback modules for the civic shell (round 11).
 *
 * Used ONLY while the role module is not delivered: CivicMap (R03), CivicEditor (R04),
 * CivicFeedback (R06). Same mount contract as CONTRACT.txt §4, so a delivery replaces
 * it without code changes in the shell. Deliberately plain: list, card, history, form.
 * All server text goes through textContent; links accept only http(s) URLs.
 */
(function () {
  "use strict";
  const LABELS = {
    kind: { construction: "Строительство", roadworks: "Дорожные работы", landscaping: "Благоустройство", event: "Мероприятие" },
    status: { planned: "Запланировано", in_progress: "Идут работы", completed: "Завершено", cancelled: "Отменено", unknown: "Статус не подтверждён" },
    evidence: { observed: "Сведения из источника", derived: "Выведено из источников", hypothesis: "Гипотеза", synthetic: "Синтетический пример" },
    publication: { draft: "Черновик", published: "Опубликовано", archived: "В архиве" },
    basis: { planned: "плановая сумма", contract: "по договору", spent: "освоено", unknown: "основание неизвестно" },
    precision: { source: "по источнику", approximate: "приблизительно", unknown: "точность неизвестна" },
    category: { roads: "Дороги", sidewalks: "Тротуары", transport_stops: "Остановки", lighting: "Освещение", landscaping: "Благоустройство", other: "Другое" },
  };
  const COLORS = { construction: "#176b4a", roadworks: "#c17238", landscaping: "#5b8f3a", event: "#3b6fb6" };
  const el = (tag, attrs, text) => {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {}))
      if (value !== null && value !== undefined && value !== false) node.setAttribute(key, value === true ? "" : value);
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  };
  const label = (group, value) => LABELS[group][value] || "нет данных";
  const date = (value) => {
    if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return "нет данных";
    const [y, m, d] = value.split("-");
    return `${d}.${m}.${y}`;
  };
  const stamp = (value) => {
    if (typeof value !== "string") return "нет данных";
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? "нет данных" : parsed.toLocaleString("ru-RU", { dateStyle: "medium", timeStyle: "short" });
  };
  const money = (budget) => {
    const amount = budget?.amount_kzt;
    if (typeof amount !== "number" || !Number.isFinite(amount)) return "нет данных";
    return amount.toLocaleString("ru-RU") + " ₸ · " + label("basis", budget.basis);
  };
  const safeUrl = (value) => {
    try {
      const url = new URL(String(value));
      return url.protocol === "http:" || url.protocol === "https:" ? url.href : null;
    } catch { return null; }
  };
  const errorText = (error) => (error && error.message) || "Запрос не выполнен.";
  function row(dl, term, value, extraClass) {
    dl.append(el("dt", null, term), el("dd", extraClass ? { class: extraClass } : null, value));
  }

  // ---------------------------------------------------------------- public map
  function mountMap({ root, map, api, onSelect, onFeedback }) {
    const P = "civic-r01-";
    const S = { items: [], selected: null, seq: 0, detailSeq: 0, kind: "", status: "", destroyed: false, handlers: [] };
    root.replaceChildren();
    const filters = el("div", { class: "civic-filters", role: "group", "aria-label": "Фильтры" });
    const kindSelect = el("select", { "aria-label": "Вид работ" });
    kindSelect.append(el("option", { value: "" }, "Все виды"));
    for (const [value, text] of Object.entries(LABELS.kind)) kindSelect.append(el("option", { value }, text));
    const statusSelect = el("select", { "aria-label": "Статус" });
    statusSelect.append(el("option", { value: "" }, "Любой статус"));
    for (const [value, text] of Object.entries(LABELS.status)) statusSelect.append(el("option", { value }, text));
    filters.append(kindSelect, statusSelect);
    const count = el("p", { class: "civic-count", role: "status", "aria-live": "polite" });
    const list = el("ul", { class: "civic-list", "aria-label": "Опубликованные записи" });
    const card = el("article", { class: "civic-card", hidden: true, "aria-live": "polite" });
    root.append(filters, count, list, card);
    try {
      const saved = JSON.parse(localStorage.getItem("civic.filters.v1") || "{}");
      if (LABELS.kind[saved.kind]) S.kind = kindSelect.value = saved.kind;
      if (LABELS.status[saved.status]) S.status = statusSelect.value = saved.status;
    } catch { /* optional convenience */ }
    const onFilter = () => {
      S.kind = kindSelect.value; S.status = statusSelect.value;
      try { localStorage.setItem("civic.filters.v1", JSON.stringify({ kind: S.kind, status: S.status })); } catch { /* ignore */ }
      void load();
    };
    kindSelect.addEventListener("change", onFilter);
    statusSelect.addEventListener("change", onFilter);

    function features() {
      return { type: "FeatureCollection", features: S.items.filter((item) => item.geometry && item.geometry.type)
        .map((item) => ({ type: "Feature", id: item.id, geometry: item.geometry,
          properties: { id: item.id, kind: item.kind, approximate: item.geometry_precision !== "source",
            synthetic: item.evidence_type === "synthetic", faded: item.status === "completed" || item.status === "cancelled" } })) };
    }
    const colorExpr = ["match", ["get", "kind"], "construction", COLORS.construction, "roadworks", COLORS.roadworks,
      "landscaping", COLORS.landscaping, "event", COLORS.event, "#6d7c76"];
    function ensureLayers() {
      if (!map || S.destroyed) return;
      if (!map.getSource(P + "objects")) {
        map.addSource(P + "objects", { type: "geojson", data: features(), promoteId: "id" });
        map.addLayer({ id: P + "fill", type: "fill", source: P + "objects", filter: ["==", ["geometry-type"], "Polygon"],
          paint: { "fill-color": colorExpr, "fill-opacity": ["case", ["get", "faded"], 0.12, 0.24] } });
        const lineFilter = (approx) => ["all", ["in", ["geometry-type"], ["literal", ["LineString", "Polygon"]]], ["==", ["get", "approximate"], approx]];
        const linePaint = { "line-color": colorExpr, "line-width": 4, "line-opacity": ["case", ["get", "faded"], 0.45, 0.9] };
        map.addLayer({ id: P + "line", type: "line", source: P + "objects", filter: lineFilter(false), paint: linePaint });
        // Approximate geometry is drawn dashed (MapLibre has no data-driven dasharray).
        map.addLayer({ id: P + "line-approx", type: "line", source: P + "objects", filter: lineFilter(true),
          paint: { ...linePaint, "line-dasharray": [2, 1.5] } });
        map.addLayer({ id: P + "point", type: "circle", source: P + "objects", filter: ["==", ["geometry-type"], "Point"],
          paint: { "circle-radius": 8, "circle-color": ["case", ["get", "approximate"], "#ffffff", colorExpr],
            "circle-stroke-color": colorExpr, "circle-stroke-width": 3, "circle-opacity": ["case", ["get", "faded"], 0.5, 1] } });
        map.addLayer({ id: P + "selected", type: "circle", source: P + "objects", filter: ["==", ["get", "id"], ""],
          paint: { "circle-radius": 14, "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": "#152c26", "circle-stroke-width": 2 } });
        const click = (event) => { const id = event.features?.[0]?.properties?.id; if (id) select(id, true); };
        const enter = () => { map.getCanvas().style.cursor = "pointer"; };
        const leave = () => { map.getCanvas().style.cursor = ""; };
        for (const layer of [P + "point", P + "line", P + "line-approx", P + "fill"]) {
          map.on("click", layer, click); map.on("mouseenter", layer, enter); map.on("mouseleave", layer, leave);
          S.handlers.push(["click", layer, click], ["mouseenter", layer, enter], ["mouseleave", layer, leave]);
        }
      } else map.getSource(P + "objects").setData(features());
      map.setFilter(P + "selected", ["==", ["get", "id"], S.selected || ""]);
    }

    async function load() {
      const seq = ++S.seq;
      count.textContent = "Загружаем опубликованные записи…";
      const params = new URLSearchParams();
      if (S.kind) params.set("kind", S.kind);
      if (S.status) params.set("status", S.status);
      const items = [];
      try {
        let cursor = null;
        for (let page = 0; page < 10; page++) {
          if (cursor) params.set("cursor", cursor);
          const query = params.toString();
          const data = await api.request("GET", "/objects" + (query ? "?" + query : ""));
          if (seq !== S.seq || S.destroyed) return;
          items.push(...(Array.isArray(data?.items) ? data.items : []));
          cursor = data?.next_cursor || null;
          if (!cursor) break;
        }
      } catch (error) {
        if (seq !== S.seq || S.destroyed) return;
        count.textContent = "Не удалось загрузить записи: " + errorText(error);
        const retry = el("button", { type: "button", class: "text-button" }, "Повторить");
        retry.addEventListener("click", () => void load());
        count.append(" ", retry);
        return;
      }
      S.items = items;
      renderList();
      ensureLayers();
      if (S.selected && !items.some((item) => item.id === S.selected)) void select(S.selected, false);
    }
    function renderList() {
      list.replaceChildren();
      const filtered = S.kind || S.status;
      count.textContent = S.items.length ? `Опубликовано записей: ${S.items.length}` + (filtered ? " (с фильтром)" : "")
        : filtered ? "По выбранным фильтрам записей нет." : "Опубликованных записей пока нет.";
      if (!S.items.length && filtered) {
        const reset = el("button", { type: "button", class: "text-button" }, "Сбросить фильтры");
        reset.addEventListener("click", () => { kindSelect.value = statusSelect.value = ""; onFilter(); });
        count.append(" ", reset);
      }
      for (const item of S.items) {
        const li = el("li");
        const button = el("button", { type: "button", class: "civic-item", "aria-pressed": String(item.id === S.selected) });
        const dot = el("i", { class: "civic-kind-dot", "aria-hidden": "true" });
        dot.style.background = COLORS[item.kind] || "#6d7c76";
        const title = el("b", null, item.title || "Без названия");
        const meta = el("span", null, `${label("kind", item.kind)} · ${label("status", item.status)}`);
        button.append(dot, title, meta);
        if (item.evidence_type === "synthetic") button.append(el("em", { class: "civic-badge synthetic" }, "синтетический пример"));
        else if (item.evidence_type === "hypothesis") button.append(el("em", { class: "civic-badge" }, "гипотеза"));
        if (!item.geometry) button.append(el("em", { class: "civic-badge" }, "без координат"));
        button.addEventListener("click", () => void select(item.id, true));
        li.append(button);
        list.append(li);
      }
    }
    async function select(id, fly) {
      S.selected = id;
      list.querySelectorAll(".civic-item").forEach((button, index) =>
        button.setAttribute("aria-pressed", String(S.items[index]?.id === id)));
      if (map && map.getLayer(P + "selected")) map.setFilter(P + "selected", ["==", ["get", "id"], id || ""]);
      if (!id) { card.hidden = true; return; }
      const seq = ++S.detailSeq;
      card.hidden = false;
      card.replaceChildren(el("p", { class: "muted" }, "Загружаем карточку…"));
      let data;
      try {
        data = await api.request("GET", "/objects/" + encodeURIComponent(id));
      } catch (error) {
        if (seq !== S.detailSeq || S.destroyed) return;
        card.replaceChildren(el("p", { class: "civic-error" }, error?.status === 404
          ? "Запись не найдена или не опубликована." : "Карточка не загрузилась: " + errorText(error)));
        return;
      }
      if (seq !== S.detailSeq || S.destroyed) return;
      renderCard(data?.item, Array.isArray(data?.history) ? data.history : []);
      if (fly) card.scrollIntoView({ block: "start", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
      if (fly && map && data?.item?.geometry) flyTo(data.item.geometry);
      onSelect?.(data?.item || { id });
    }
    function flyTo(geometry) {
      try {
        const coords = geometry.type === "Point" ? [geometry.coordinates] : geometry.type === "LineString"
          ? geometry.coordinates : geometry.coordinates.flat();
        const bounds = coords.reduce((b, c) => b.extend(c), new maplibregl.LngLatBounds(coords[0], coords[0]));
        const mobile = innerWidth < 761;
        map.fitBounds(bounds, { maxZoom: 15.5, duration: matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 700,
          padding: mobile ? { top: 90, left: 30, right: 60, bottom: Math.round(innerHeight * 0.5) } : { top: 130, left: 480, right: 100, bottom: 80 } });
      } catch (error) { console.warn("civic fly", error); }
    }
    function renderCard(item, history) {
      card.replaceChildren();
      if (!item) { card.append(el("p", { class: "civic-error" }, "Запись не найдена.")); return; }
      const head = el("header");
      head.append(el("span", { class: "eyebrow" }, `${label("kind", item.kind)} · ${label("status", item.status)}`), el("h2", null, item.title || "Без названия"));
      if (item.evidence_type === "synthetic") head.append(el("p", { class: "civic-badge synthetic block" }, "Синтетический пример: не сведения о реальных работах."));
      else head.append(el("p", { class: "civic-badge block" }, label("evidence", item.evidence_type)));
      card.append(head);
      if (item.description) card.append(el("p", { class: "civic-desc" }, item.description));
      const schedule = item.schedule || {};
      const dl = el("dl", { class: "civic-facts" });
      row(dl, "Начало по плану", date(schedule.planned_start));
      row(dl, "Первоначальный срок", date(schedule.original_planned_end));
      const moved = schedule.original_planned_end && schedule.current_planned_end && schedule.original_planned_end !== schedule.current_planned_end;
      row(dl, "Текущий плановый срок", date(schedule.current_planned_end) + (moved ? " · срок перенесён" : ""), moved ? "civic-moved" : null);
      row(dl, "Фактическое завершение", schedule.actual_end ? date(schedule.actual_end) : "не подтверждено");
      row(dl, "Стоимость", money(item.budget));
      row(dl, "Ответственный", item.responsible?.organization || "нет данных");
      if (item.responsible?.public_contact) row(dl, "Контакт", item.responsible.public_contact);
      row(dl, "Место", item.geometry ? label("precision", item.geometry_precision) : "координаты не указаны");
      row(dl, "Обновлено", stamp(item.updated_at) + ` · версия ${Number.isInteger(item.revision) ? item.revision : "?"}`);
      card.append(dl);
      const sources = Array.isArray(item.source_refs) ? item.source_refs : [];
      const sourceBox = el("section", { class: "civic-sources" });
      sourceBox.append(el("h3", null, "Источники"));
      if (!sources.length) sourceBox.append(el("p", { class: "muted" }, "Источник не указан."));
      for (const ref of sources) {
        const p = el("p");
        const href = safeUrl(ref?.url);
        const name = ref?.publisher || ref?.id || "источник";
        if (href) p.append(el("a", { href, target: "_blank", rel: "noopener noreferrer nofollow" }, name));
        else p.append(document.createTextNode(name));
        const status = ref?.access_status === "fetched" ? "получен" : ref?.access_status === "unavailable" ? "недоступен" : "не загружался";
        p.append(document.createTextNode(` · опубликовано ${date(ref?.published_on)} · ${status}` + (ref?.license ? ` · ${ref.license}` : " · условия использования не указаны")));
        sourceBox.append(p);
      }
      if (item.evidence_notes) sourceBox.append(el("p", { class: "muted" }, item.evidence_notes));
      card.append(sourceBox);
      const historyBox = el("section", { class: "civic-history" });
      historyBox.append(el("h3", null, "История изменений"));
      if (!history.length) historyBox.append(el("p", { class: "muted" }, "Опубликованных изменений нет."));
      const ol = el("ol");
      for (const entry of history) {
        const li = el("li");
        li.append(el("b", null, stamp(entry?.at)), document.createTextNode(` · версия ${entry?.revision ?? "?"}`));
        const fields = Array.isArray(entry?.changed_fields) ? entry.changed_fields.join(", ") : "";
        if (fields) li.append(el("span", { class: "muted" }, " · " + fields));
        if (entry?.reason) li.append(el("p", null, "Причина: " + entry.reason));
        if (entry?.public_actor_label) li.append(el("p", { class: "muted" }, entry.public_actor_label));
        ol.append(li);
      }
      historyBox.append(ol);
      card.append(historyBox);
      const ask = el("button", { type: "button", class: "btn primary civic-ask" }, "Сообщить о проблеме или предложении");
      ask.addEventListener("click", () => onFeedback?.({ objectId: item.id, geometry: null }));
      card.append(ask);
    }

    void load();
    return {
      refresh: () => load(),
      selectObject: (id) => select(id, true),
      destroy() {
        S.destroyed = true; S.seq++; S.detailSeq++;
        if (map) {
          for (const [type, layer, handler] of S.handlers) map.off(type, layer, handler);
          for (const id of [P + "selected", P + "point", P + "line-approx", P + "line", P + "fill"]) if (map.getLayer(id)) map.removeLayer(id);
          if (map.getSource(P + "objects")) map.removeSource(P + "objects");
          map.getCanvas().style.cursor = "";
        }
        root.replaceChildren();
      },
    };
  }

  // ---------------------------------------------------------------- feedback
  function mountFeedback({ root, api, objectId, geometry }) {
    const S = { busy: false, destroyed: false, sent: null };
    root.replaceChildren();
    const form = el("form", { class: "civic-form", novalidate: true });
    form.append(el("p", { class: "civic-note" }, "Сообщение остаётся на этой платформе. Официальная регистрация обращения (iKOMEK, eOtinish) не выполняется."));
    const category = el("select", { name: "category", required: true });
    for (const [value, text] of Object.entries(LABELS.category)) category.append(el("option", { value }, text));
    const text = el("textarea", { name: "text", rows: "4", maxlength: "2000", required: true, placeholder: "Что происходит и где именно" });
    const consent = el("input", { type: "checkbox", name: "consent_public" });
    const consentLabel = el("label", { class: "civic-check" });
    consentLabel.append(consent, document.createTextNode(" Разрешаю опубликовать текст после проверки редактором"));
    const status = el("p", { class: "civic-form-status", role: "status", "aria-live": "polite" });
    const submit = el("button", { type: "submit", class: "btn primary" }, "Отправить");
    const lab = (title, field) => { const l = el("label", { class: "civic-field" }); l.append(el("span", null, title), field); return l; };
    form.append(lab("Тема", category), lab("Сообщение", text), consentLabel, submit, status);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (S.busy) return;
      const value = text.value.trim();
      if (!value) { status.textContent = "Напишите текст сообщения."; text.focus(); return; }
      S.busy = true; submit.disabled = true; status.textContent = "Отправляем…";
      try {
        const data = await api.request("POST", "/feedback", { object_id: objectId || null, geometry: objectId ? null : geometry || null,
          category: category.value, text: value, consent_public: consent.checked });
        if (S.destroyed) return;
        S.sent = data;
        form.replaceChildren(el("p", { class: "civic-receipt" }, `Сообщение сохранено. Номер: ${data?.receipt_id ?? "—"}. Статус: ожидает проверки редактором.`),
          el("p", { class: "muted" }, "Это не официальное обращение и не означает, что работы начаты."));
      } catch (error) {
        if (S.destroyed) return;
        status.textContent = "Не отправлено: " + errorText(error) + " Текст сохранён в форме.";
      } finally {
        S.busy = false; if (!S.destroyed) submit.disabled = false;
      }
    });
    root.append(form);
    const published = el("section", { class: "civic-public-feedback" });
    root.append(published);
    if (objectId) {
      api.request("GET", "/objects/" + encodeURIComponent(objectId) + "/feedback").then((data) => {
        if (S.destroyed) return;
        const items = Array.isArray(data?.items) ? data.items : [];
        published.append(el("h3", null, items.length ? "Опубликованные сообщения" : "Опубликованных сообщений пока нет"));
        for (const item of items) {
          const p = el("div", { class: "civic-msg" });
          p.append(el("p", null, item.text || ""), el("p", { class: "muted" }, `${label("category", item.category)} · ${stamp(item.created_at || item.at)}`));
          if (item.public_reply) p.append(el("p", { class: "civic-reply" }, "Ответ редактора: " + item.public_reply));
          published.append(p);
        }
      }).catch(() => { /* list is optional; the form still works */ });
    }
    return { destroy() { S.destroyed = true; root.replaceChildren(); } };
  }

  // ---------------------------------------------------------------- editor
  function mountEditor({ root, map, api, onPublished }) {
    const S = { destroyed: false, view: "list", current: null, picking: false, busy: false, unsub: null, mapClick: null };
    root.replaceChildren();
    const status = el("p", { class: "civic-form-status", role: "status", "aria-live": "polite" });
    const body = el("div");
    root.append(body, status);
    const say = (text) => { status.textContent = text || ""; };

    function stopPicking() {
      if (S.mapClick && map) map.off("click", S.mapClick);
      S.mapClick = null; S.picking = false;
      if (map) map.getCanvas().style.cursor = "";
    }
    function render() {
      stopPicking();
      body.replaceChildren();
      const session = api.session;
      if (!session.checked) { body.append(el("p", { class: "muted" }, "Проверяем вход…")); return; }
      if (!session.authenticated) return renderLogin();
      const bar = el("div", { class: "civic-editor-bar" });
      bar.append(el("span", null, `Вы вошли: ${session.user?.name || "сотрудник"}`));
      const logout = el("button", { type: "button", class: "text-button" }, "Выйти");
      logout.addEventListener("click", async () => { try { await api.logout(); } catch (error) { say(errorText(error)); } render(); });
      bar.append(logout);
      const tabs = el("div", { class: "civic-tabs", role: "group" });
      for (const [view, text] of [["list", "Записи"], ["new", "Новая запись"], ["feedback", "Сообщения"]]) {
        const b = el("button", { type: "button", "aria-pressed": String(S.view === view) }, text);
        b.addEventListener("click", () => { S.view = view; S.current = null; render(); });
        tabs.append(b);
      }
      body.append(bar, tabs);
      if (S.view === "new") renderForm(null, []);
      else if (S.view === "object" && S.current) renderForm(S.current.item, S.current.history);
      else if (S.view === "feedback") void renderQueue();
      else void renderList();
    }
    function renderLogin() {
      const form = el("form", { class: "civic-form" });
      const user = el("input", { name: "username", autocomplete: "username", required: true });
      const pass = el("input", { name: "password", type: "password", autocomplete: "current-password", required: true });
      const lab = (t, f) => { const l = el("label", { class: "civic-field" }); l.append(el("span", null, t), f); return l; };
      const submit = el("button", { type: "submit", class: "btn primary" }, "Войти");
      form.append(el("p", { class: "muted" }, "Вход для сотрудников. Учётная запись создаётся администратором сервера из командной строки."),
        lab("Логин", user), lab("Пароль", pass), submit);
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        submit.disabled = true; say("Входим…");
        try { await api.login(user.value.trim(), pass.value); say(""); render(); }
        catch (error) { pass.value = ""; say("Вход не выполнен: " + errorText(error)); }
        finally { submit.disabled = false; }
      });
      body.append(form);
      user.focus();
    }
    async function renderList() {
      const box = el("div");
      body.append(box);
      box.append(el("p", { class: "muted" }, "Загружаем записи…"));
      try {
        const data = await api.request("GET", "/staff/objects");
        if (S.destroyed) return;
        box.replaceChildren();
        const items = Array.isArray(data?.items) ? data.items : [];
        if (!items.length) box.append(el("p", { class: "muted" }, "Записей пока нет. Создайте первую."));
        const ul = el("ul", { class: "civic-list" });
        for (const item of items) {
          const b = el("button", { type: "button", class: "civic-item" });
          b.append(el("b", null, item.title || "Без названия"), el("span", null, `${label("publication", item.publication)} · ${label("status", item.status)} · версия ${item.revision}`));
          b.addEventListener("click", () => void openObject(item.id));
          const li = el("li"); li.append(b); ul.append(li);
        }
        box.append(ul);
      } catch (error) {
        if (S.destroyed) return;
        box.replaceChildren(el("p", { class: "civic-error" }, errorText(error)));
        if (error?.status === 401) render();
      }
    }
    async function openObject(id) {
      // Keeps the last status line (e.g. "Опубликовано") visible after the reload.
      try {
        const data = await api.request("GET", "/staff/objects/" + encodeURIComponent(id));
        if (S.destroyed) return;
        S.current = { item: data.item, history: Array.isArray(data.history) ? data.history : [] };
        S.view = "object"; render();
      } catch (error) { say(errorText(error)); }
    }
    function input(name, value, attrs) { return el("input", { name, value: value ?? "", ...(attrs || {}) }); }
    function select(name, group, value, empty) {
      const s = el("select", { name });
      if (empty) s.append(el("option", { value: "" }, empty));
      for (const [k, t] of Object.entries(LABELS[group])) s.append(el("option", { value: k }, t));
      s.value = value ?? (empty ? "" : Object.keys(LABELS[group])[0]);
      return s;
    }
    function renderForm(item, history) {
      const isNew = !item;
      const form = el("form", { class: "civic-form civic-editor-form", novalidate: true });
      const lab = (t, f, hint) => { const l = el("label", { class: "civic-field" }); l.append(el("span", null, t), f); if (hint) l.append(el("small", null, hint)); return l; };
      const sch = item?.schedule || {};
      const f = {
        title: input("title", item?.title, { maxlength: "200", required: true }),
        kind: select("kind", "kind", item?.kind),
        status: select("status", "status", item?.status || "unknown"),
        description: el("textarea", { name: "description", rows: "3", maxlength: "4000" }),
        planned_start: input("planned_start", sch.planned_start, { type: "date" }),
        original_planned_end: input("original_planned_end", sch.original_planned_end, { type: "date" }),
        current_planned_end: input("current_planned_end", sch.current_planned_end, { type: "date" }),
        actual_end: input("actual_end", sch.actual_end, { type: "date" }),
        amount: input("amount_kzt", item?.budget?.amount_kzt ?? "", { type: "number", min: "0", step: "1", inputmode: "numeric" }),
        basis: select("basis", "basis", item?.budget?.basis || "unknown"),
        organization: input("organization", item?.responsible?.organization, { maxlength: "200" }),
        contact: input("public_contact", item?.responsible?.public_contact, { maxlength: "200" }),
        evidence: select("evidence_type", "evidence", item?.evidence_type ?? "", "— выберите —"),
        notes: el("textarea", { name: "evidence_notes", rows: "2", maxlength: "2000" }),
        lon: input("lon", item?.geometry?.type === "Point" ? item.geometry.coordinates[0] : "", { inputmode: "decimal" }),
        lat: input("lat", item?.geometry?.type === "Point" ? item.geometry.coordinates[1] : "", { inputmode: "decimal" }),
        precision: select("geometry_precision", "precision", item?.geometry_precision || "approximate"),
        reason: input("reason", "", { maxlength: "500" }),
      };
      f.description.value = item?.description || "";
      if (S.keepReason) { f.reason.value = S.keepReason; S.keepReason = ""; }
      f.notes.value = item?.evidence_notes || "";
      const published = item && item.publication === "published";
      if (published) f.original_planned_end.disabled = true;
      const pick = el("button", { type: "button", class: "btn" }, "Указать на карте");
      pick.disabled = !map;
      pick.addEventListener("click", () => {
        if (!map) return;
        stopPicking();
        S.picking = true; map.getCanvas().style.cursor = "crosshair"; say("Щёлкните по карте, чтобы поставить точку.");
        S.mapClick = (event) => { f.lon.value = event.lngLat.lng.toFixed(6); f.lat.value = event.lngLat.lat.toFixed(6); stopPicking(); say("Точка выбрана. Проверьте координаты."); };
        map.once("click", S.mapClick);
      });
      const clear = el("button", { type: "button", class: "text-button" }, "Без координат");
      clear.addEventListener("click", () => { f.lon.value = f.lat.value = ""; });
      const head = el("header");
      head.append(el("h3", null, isNew ? "Новая запись (черновик)" : (item.title || "Запись")));
      if (!isNew) head.append(el("p", { class: "muted" }, `${label("publication", item.publication)} · версия ${item.revision} · id ${item.id}`));
      if (!isNew && item.publication === "published" && item.staff?.has_unpublished_changes)
        head.append(el("p", { class: "civic-note" }, "Есть неопубликованные изменения: жители видят прежнюю версию, пока вы не нажмёте «Опубликовать изменения»."));
      form.append(head,
        lab("Название", f.title), lab("Вид", f.kind), lab("Статус работ", f.status, "Без подтверждения состояния — «Статус не подтверждён»."),
        lab("Описание", f.description),
        lab("Начало по плану", f.planned_start), lab("Первоначальный плановый срок", f.original_planned_end, published ? "После публикации не меняется." : "Неизвестную дату оставьте пустой."),
        lab("Текущий плановый срок", f.current_planned_end), lab("Фактически завершено", f.actual_end, "Только при подтверждённом завершении."),
        lab("Стоимость, ₸", f.amount, "Пусто — нет данных (не ноль)."), lab("Основание суммы", f.basis),
        lab("Ответственная организация", f.organization), lab("Публичный контакт", f.contact),
        lab("Тип сведений", f.evidence), lab("Пояснение к источнику", f.notes));
      const geo = el("fieldset", { class: "civic-geo" });
      geo.append(el("legend", null, "Место"), lab("Долгота", f.lon), lab("Широта", f.lat), lab("Точность", f.precision), pick, clear);
      form.append(geo);
      if (!isNew) form.append(lab("Причина изменения", f.reason, published ? "Обязательна для опубликованной записи." : null));
      const actions = el("div", { class: "civic-actions" });
      const save = el("button", { type: "submit", class: "btn primary" }, isNew ? "Сохранить черновик" : "Сохранить изменения");
      actions.append(save);
      let publish = null, archive = null;
      const unpublished = !!item?.staff?.has_unpublished_changes;
      if (!isNew && (item.publication === "draft" || (item.publication === "published" && unpublished))) {
        publish = el("button", { type: "button", class: "btn" }, item.publication === "draft" ? "Опубликовать" : "Опубликовать изменения");
        actions.append(publish);
      }
      if (!isNew && item.publication !== "archived") {
        archive = el("button", { type: "button", class: "btn" }, "В архив");
        actions.append(archive);
      }
      form.append(actions);

      function collect() {
        const num = (value) => value === "" ? null : Number(value);
        const lon = num(f.lon.value.trim()), lat = num(f.lat.value.trim());
        const amount = f.amount.value.trim();
        const geometry = lon === null && lat === null ? null : { type: "Point", coordinates: [lon, lat] };
        const value = {
          title: f.title.value.trim(), kind: f.kind.value, status: f.status.value, description: f.description.value.trim(),
          schedule: { planned_start: f.planned_start.value || null, original_planned_end: f.original_planned_end.value || null,
            current_planned_end: f.current_planned_end.value || null, actual_end: f.actual_end.value || null },
          budget: { amount_kzt: amount === "" ? null : Number(amount), basis: f.basis.value, source_id: item?.budget?.source_id ?? null },
          responsible: { organization: f.organization.value.trim() || null, public_contact: f.contact.value.trim() || null },
          evidence_type: f.evidence.value, evidence_notes: f.notes.value.trim(),
          geometry, geometry_precision: geometry ? f.precision.value : "unknown",
        };
        if (published) delete value.schedule.original_planned_end;
        return value;
      }
      function validate(value) {
        if (!value.title) return "Укажите название.";
        if (!value.evidence_type) return "Выберите тип сведений.";
        const g = value.geometry;
        if (g && (![g.coordinates[0], g.coordinates[1]].every(Number.isFinite) || Math.abs(g.coordinates[0]) > 180 || Math.abs(g.coordinates[1]) > 90))
          return "Координаты должны быть числами: долгота и широта.";
        if (value.budget.amount_kzt !== null && !(Number.isFinite(value.budget.amount_kzt) && value.budget.amount_kzt >= 0))
          return "Стоимость — неотрицательное число или пусто.";
        return null;
      }
      const canon = (value) => JSON.stringify(value ?? null, (key, v) => v && typeof v === "object" && !Array.isArray(v)
        ? Object.fromEntries(Object.keys(v).sort().map((k) => [k, v[k]])) : v);
      function diff(before, after) {
        const changes = {};
        for (const [key, value] of Object.entries(after)) {
          let old = before[key];
          if (key === "schedule" && published && old) { old = { ...old }; delete old.original_planned_end; }
          if (key === "description" || key === "evidence_notes") old = old || "";
          if (canon(old) !== canon(value)) changes[key] = value;
        }
        return changes;
      }
      async function guarded(action) {
        if (S.busy) return;
        S.busy = true;
        for (const b of form.querySelectorAll("button")) b.disabled = true;
        try { await action(); }
        catch (error) {
          if (S.destroyed) return;
          if (error?.status === 409) say("Запись уже изменил другой сотрудник (версия устарела). Ваш текст сохранён в форме — откройте запись заново и перенесите правки.");
          else if (error?.status === 401) { say("Сессия закончилась. Войдите снова — текст формы не отправлен."); }
          else say("Не сохранено: " + errorText(error) + (error?.fields ? " " + Object.entries(error.fields).map(([k, v]) => `${k}: ${v}`).join("; ") : ""));
        } finally {
          S.busy = false;
          if (!S.destroyed) for (const b of form.querySelectorAll("button")) b.disabled = false;
          if (!map) pick.disabled = true;
        }
      }
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        const value = collect();
        const problem = validate(value);
        if (problem) { say(problem); return; }
        void guarded(async () => {
          if (isNew) {
            const data = await api.request("POST", "/staff/objects", value);
            say("Черновик сохранён. Он не виден жителям до публикации.");
            await openObject(data.item.id);
          } else {
            const changes = diff(item, value);
            if (!Object.keys(changes).length) { say("Изменений нет."); return; }
            const reason = f.reason.value.trim();
            if (published && !reason) { say("Укажите причину изменения опубликованной записи."); f.reason.focus(); return; }
            const data = await api.request("POST", `/staff/objects/${encodeURIComponent(item.id)}/update`, { expected_revision: item.revision, changes, reason: reason || null });
            say(published ? "Изменения сохранены. Нажмите «Опубликовать изменения», чтобы их увидели жители." : "Изменения сохранены.");
            S.keepReason = reason;
            await openObject(item.id);
          }
        });
      });
      publish?.addEventListener("click", () => void guarded(async () => {
        const first = item.publication === "draft" && !item.staff?.first_published_at;
        const reason = f.reason.value.trim() || (first ? "Первая публикация" : "");
        if (!reason) { say("Укажите причину изменения — её увидят жители в истории."); f.reason.focus(); return; }
        const data = await api.request("POST", `/staff/objects/${encodeURIComponent(item.id)}/publish`, { expected_revision: item.revision, reason });
        say("Опубликовано. Запись видна на карте.");
        onPublished?.(data?.item || item);
        await openObject(item.id);
      }));
      archive?.addEventListener("click", () => void guarded(async () => {
        const reason = f.reason.value.trim();
        if (!reason) { say("Укажите причину переноса в архив."); f.reason.focus(); return; }
        await api.request("POST", `/staff/objects/${encodeURIComponent(item.id)}/archive`, { expected_revision: item.revision, reason });
        say("Запись перенесена в архив и скрыта с публичной карты.");
        onPublished?.(null);
        await openObject(item.id);
      }));
      body.append(form);
      if (!isNew) {
        const h = el("section", { class: "civic-history" });
        h.append(el("h3", null, "История (служебная)"));
        const ol = el("ol");
        for (const entry of history) {
          const li = el("li");
          li.append(el("b", null, stamp(entry?.at)), document.createTextNode(` · версия ${entry?.revision ?? "?"} · ${(entry?.changed_fields || []).join(", ")}`));
          if (entry?.reason) li.append(el("p", null, "Причина: " + entry.reason));
          ol.append(li);
        }
        if (!history.length) h.append(el("p", { class: "muted" }, "Изменений ещё нет."));
        h.append(ol);
        body.append(h);
      }
    }
    async function renderQueue() {
      const box = el("div");
      body.append(box);
      box.append(el("p", { class: "muted" }, "Загружаем очередь…"));
      try {
        const data = await api.request("GET", "/staff/feedback");
        if (S.destroyed) return;
        box.replaceChildren();
        const items = Array.isArray(data?.items) ? data.items : [];
        if (!items.length) box.append(el("p", { class: "muted" }, "Сообщений на проверке нет."));
        for (const msg of items) {
          const card = el("div", { class: "civic-msg" });
          card.append(el("p", null, msg.text || ""),
            el("p", { class: "muted" }, `${label("category", msg.category)} · ${msg.moderation || "pending"} · публикация текста ${msg.consent_public ? "разрешена" : "не разрешена"} · объект ${msg.object_id || "—"}`));
          if (msg.moderation === "pending") {
            const reason = input("reason", "", { maxlength: "300", placeholder: "Причина решения" });
            const reply = input("public_reply", "", { maxlength: "1000", placeholder: "Публичный ответ (необязательно)" });
            const approve = el("button", { type: "button", class: "btn primary" }, "Одобрить");
            const reject = el("button", { type: "button", class: "btn" }, "Отклонить");
            const act = async (action) => {
              if (!reason.value.trim()) { say("Укажите причину решения."); reason.focus(); return; }
              try {
                await api.request("POST", `/staff/feedback/${encodeURIComponent(msg.id)}/moderate`, { expected_revision: msg.revision,
                  action, reason: reason.value.trim(), public_reply: reply.value.trim() || null });
                say(action === "approve" ? "Сообщение одобрено." : "Сообщение отклонено.");
                render();
              } catch (error) { say(errorText(error)); }
            };
            approve.addEventListener("click", () => void act("approve"));
            reject.addEventListener("click", () => void act("reject"));
            card.append(reason, reply, approve, reject);
          }
          box.append(card);
        }
      } catch (error) {
        if (S.destroyed) return;
        box.replaceChildren(el("p", { class: "civic-error" }, error?.code === "module_unavailable" ? "Модуль сообщений не подключён." : errorText(error)));
      }
    }
    S.unsub = api.onSession(() => { if (!S.busy) render(); });
    if (!api.session.checked) api.refreshSession().catch((error) => { say(errorText(error)); render(); });
    render();
    return {
      openObject: (id) => void openObject(id),
      destroy() { S.destroyed = true; stopPicking(); S.unsub?.(); root.replaceChildren(); },
    };
  }

  window.CivicShellFallback = {
    map: { mount: mountMap },
    feedback: { mount: mountFeedback },
    editor: { mount: mountEditor },
    labels: LABELS,
  };
})();
