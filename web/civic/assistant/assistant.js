/*
 * R09 CivicAssistant — помощник по проверенным фактам карточки (раунд 11, civic-v1).
 *
 * window.CivicAssistant.mount({root, api, objectId, scenarioId?}) -> {destroy}
 *   Житель задаёт вопрос; сервер (POST /assistant) собирает ответ из опубликованных
 *   фактов. Браузер не передаёт фактов: только {question, object_id, scenario_id}.
 * window.CivicAssistant.mountDraftReview({root, api, onApplyField}) -> {destroy}
 *   Редактор вставляет текст публикации, получает черновик полей
 *   (POST /staff/assistant/extract) и вручную переносит отмеченные поля в форму
 *   через onApplyField(field, value, evidence). Ничего не публикуется отсюда.
 *
 * Правила: только textContent/createElement (никакого innerHTML для ответов сервера),
 * один активный запрос: новый вопрос/смена объекта/destroy отменяют прежний
 * (AbortController + номер запроса), запоздавший ответ отбрасывается. Классы и
 * id имеют префикс civic-r09-. Компонент не трогает document.body и чужие globals.
 */
(function (global) {
  "use strict";

  const MAX_QUESTION = 500;
  const MAX_TEXT = 20000;
  const CLIENT_TIMEOUT_MS = 20000;

  const EXAMPLES = [
    "Что здесь происходит?",
    "Когда закончат работы?",
    "Почему перенесли срок?",
    "Кто отвечает за работы?",
    "Сколько это стоит и откуда сумма?",
    "Откуда эти данные?",
    "Работы уже закончены?",
    "Не болып жатыр? Қашан аяқталады?",
  ];
  const SCENARIO_EXAMPLES = ["Чем план A отличается от B?", "Как изменится проход?"];

  const SOURCE_LABELS = {
    template: "Ответ собран по данным карточки (шаблон, без модели)",
    llm: "Тип ответа выбран моделью; текст, даты и суммы — из данных карточки",
    unavailable: "Помощник не может ответить",
  };
  const KIND_LABELS = { quote: "цитата из карточки", missing: "нет данных", notice: "пометка", derived: "вычислено по датам/метрикам" };
  const FIELD_LABELS = {
    title: "Название",
    kind: "Тип",
    "schedule.planned_start": "Плановое начало",
    "schedule.current_planned_end": "Текущий плановый срок окончания",
    "budget.amount_kzt": "Сумма, ₸",
    "budget.basis": "Основание суммы",
    "responsible.organization": "Ответственная организация",
    location_text: "Место (текстом)",
  };
  const CONFIDENCE_LABELS = {
    exact_date: "точная дата в тексте",
    partial_date: "дата неполная — значение не заполнено",
    invalid_date: "дата некорректна — значение не заполнено",
    conflict: "в тексте противоречия — выберите вручную",
    unit_conversion: "сумма с единицами (млн/млрд) пересчитана кодом",
    exact_pattern: "найдено по шаблону",
    pattern_match: "найдено по шаблону",
    keyword: "по ключевому слову",
    keyword_near_amount: "по слову рядом с суммой",
    default_unknown: "основание не найдено",
    heuristic_first_sentence: "первое предложение — переформулируйте",
    quote_only: "только цитата",
  };

  function el(tag, attrs, text) {
    const node = document.createElement(tag);
    if (attrs) {
      for (const [key, value] of Object.entries(attrs)) {
        if (value === null || value === undefined || value === false) continue;
        if (key === "className") node.className = value;
        else node.setAttribute(key, value === true ? "" : String(value));
      }
    }
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function errorMessage(error) {
    const status = error && typeof error.status === "number" ? error.status : 0;
    const code = error && typeof error.code === "string" ? error.code : "";
    if (status === 429 || code === "rate_limited") return "Слишком много вопросов подряд. Повторите через минуту.";
    if (code === "question_too_long" || status === 413) return "Вопрос слишком длинный: до " + MAX_QUESTION + " символов.";
    if (status === 401) return "Нужен вход сотрудника.";
    if (status === 403) return "Недостаточно прав или запрос отклонён проверкой безопасности.";
    if (code === "timeout") return "Сервер не ответил вовремя. Сведения карточки доступны выше.";
    if (status === 400 || status === 422) return "Запрос не принят: проверьте текст вопроса.";
    return "Помощник сейчас недоступен. Сведения карточки доступны выше.";
  }

  // Один активный запрос: start() отменяет предыдущий; isCurrent(id) отсекает запоздавшие ответы.
  function requestGate() {
    let seq = 0;
    let controller = null;
    return {
      start() {
        if (controller) controller.abort();
        controller = typeof AbortController === "function" ? new AbortController() : null;
        seq += 1;
        return { id: seq, signal: controller ? controller.signal : undefined };
      },
      cancel() {
        if (controller) controller.abort();
        controller = null;
        seq += 1;
      },
      isCurrent(id) {
        return id === seq;
      },
    };
  }

  function renderAnswer(box, data) {
    box.replaceChildren();
    const source = typeof data.source === "string" && SOURCE_LABELS[data.source] ? data.source : "unavailable";
    const head = el("div", { className: "civic-r09-answer-head" });
    head.append(el("span", { className: "civic-r09-badge civic-r09-badge--" + source, "data-source": source }, SOURCE_LABELS[source]));
    box.append(head);
    const list = el("ul", { className: "civic-r09-statements" });
    const statements = Array.isArray(data.statements) ? data.statements : [];
    for (const st of statements) {
      if (!st || typeof st.text !== "string") continue;
      const kind = typeof st.kind === "string" ? st.kind : "fact";
      const item = el("li", { className: "civic-r09-st civic-r09-st--" + kind.replace(/[^a-z_]/g, "") });
      item.append(el("span", { className: "civic-r09-st-text" }, st.text));
      if (KIND_LABELS[kind]) item.append(el("span", { className: "civic-r09-st-kind" }, KIND_LABELS[kind]));
      const sources = Array.isArray(st.source_ids) ? st.source_ids.filter((s) => typeof s === "string") : [];
      if (sources.length) item.append(el("span", { className: "civic-r09-st-src" }, "источник: " + sources.join(", ")));
      const facts = Array.isArray(st.fact_ids) ? st.fact_ids.filter((s) => typeof s === "string") : [];
      if (facts.length) item.setAttribute("data-fact-ids", facts.join(" "));
      list.append(item);
    }
    if (!list.childElementCount) list.append(el("li", { className: "civic-r09-st civic-r09-st--missing" }, "Нет данных для ответа."));
    box.append(list);
    const warnings = Array.isArray(data.warnings) ? data.warnings : [];
    if (warnings.some((w) => typeof w === "string" && w.startsWith("audit_dropped"))) {
      box.append(el("p", { className: "civic-r09-note" }, "Часть ответа скрыта автоматической проверкой: она не подтверждалась данными карточки."));
    }
    const meta = [];
    if (typeof data.facts_version === "string") meta.push(data.facts_version);
    if (typeof data.mode === "string") meta.push("режим: " + data.mode);
    if (meta.length) box.append(el("p", { className: "civic-r09-meta" }, meta.join(" · ")));
  }

  function mount(options) {
    const opts = options || {};
    const root = opts.root;
    const api = opts.api;
    if (!root || typeof root.append !== "function") throw new TypeError("CivicAssistant.mount: root is required");
    if (!api || typeof api.request !== "function") throw new TypeError("CivicAssistant.mount: api.request is required");
    const objectId = typeof opts.objectId === "string" && opts.objectId ? opts.objectId : null;
    const scenarioId = typeof opts.scenarioId === "string" && opts.scenarioId ? opts.scenarioId : null;
    const gate = requestGate();
    let destroyed = false;
    let clientTimer = null;

    const section = el("section", { className: "civic-r09", "aria-label": "Вопрос по объекту" });
    section.append(el("h3", { className: "civic-r09-title" }, "Спросить о проекте"));
    section.append(el("p", { className: "civic-r09-hint" },
      "Помощник отвечает только по опубликованным сведениям карточки. Если данных нет, он так и скажет."));
    const examples = el("div", { className: "civic-r09-examples", role: "list" });
    for (const q of objectId ? EXAMPLES : []) examples.append(el("button", { type: "button", className: "civic-r09-chip", role: "listitem" }, q));
    for (const q of scenarioId ? SCENARIO_EXAMPLES : []) examples.append(el("button", { type: "button", className: "civic-r09-chip", role: "listitem" }, q));
    const form = el("form", { className: "civic-r09-form", novalidate: true });
    const inputId = "civic-r09-q-" + Math.random().toString(36).slice(2, 8);
    form.append(el("label", { className: "civic-r09-sr", for: inputId }, "Ваш вопрос"));
    const input = el("textarea", { id: inputId, className: "civic-r09-input", rows: "2", maxlength: String(MAX_QUESTION),
      placeholder: "Например: когда закончат работы?" });
    const counter = el("span", { className: "civic-r09-counter", "aria-hidden": "true" }, "0/" + MAX_QUESTION);
    const ask = el("button", { type: "submit", className: "civic-r09-ask" }, "Спросить");
    const cancel = el("button", { type: "button", className: "civic-r09-cancel", hidden: true }, "Отменить");
    const row = el("div", { className: "civic-r09-row" });
    row.append(counter, cancel, ask);
    form.append(input, row);
    const status = el("p", { className: "civic-r09-status", role: "status", "aria-live": "polite" });
    const answer = el("div", { className: "civic-r09-answer", "aria-live": "polite" });
    section.append(examples, form, status, answer);
    root.append(section);

    function setPending(pending) {
      ask.disabled = pending;
      cancel.hidden = !pending;
      section.setAttribute("aria-busy", pending ? "true" : "false");
      status.textContent = pending ? "Ищу ответ в данных карточки…" : "";
    }

    function clearTimer() {
      if (clientTimer !== null) clearTimeout(clientTimer);
      clientTimer = null;
    }

    async function submit(question) {
      const q = String(question || "").trim();
      if (!q) {
        status.textContent = "Введите вопрос.";
        return;
      }
      if (q.length > MAX_QUESTION) {
        status.textContent = errorMessage({ code: "question_too_long" });
        return;
      }
      const ticket = gate.start();
      clearTimer();
      setPending(true);
      answer.replaceChildren();
      clientTimer = setTimeout(() => {
        if (destroyed || !gate.isCurrent(ticket.id)) return;
        gate.cancel();
        setPending(false);
        status.textContent = errorMessage({ code: "timeout" });
      }, CLIENT_TIMEOUT_MS);
      try {
        const data = await api.request("POST", "/assistant", { question: q, object_id: objectId, scenario_id: scenarioId },
          { signal: ticket.signal, timeoutMs: CLIENT_TIMEOUT_MS });
        if (destroyed || !gate.isCurrent(ticket.id)) return; // запоздавший ответ на прежний вопрос
        clearTimer();
        setPending(false);
        if (!data || typeof data !== "object") throw { code: "bad_response" };
        // Ответ должен относиться к этой карточке; иначе это ответ про другой объект.
        if ((data.object_id ?? null) !== objectId && data.source !== "unavailable") {
          status.textContent = "Ответ относится к другому объекту и не показан.";
          return;
        }
        renderAnswer(answer, data);
      } catch (error) {
        if (destroyed || !gate.isCurrent(ticket.id)) return;
        clearTimer();
        setPending(false);
        if (error && error.code === "aborted") return;
        status.textContent = errorMessage(error);
      }
    }

    const onSubmit = (event) => {
      event.preventDefault();
      submit(input.value);
    };
    const onChip = (event) => {
      const chip = event.target.closest ? event.target.closest(".civic-r09-chip") : null;
      if (!chip || !examples.contains(chip)) return;
      input.value = chip.textContent;
      onInput();
      submit(chip.textContent);
    };
    const onInput = () => {
      counter.textContent = input.value.length + "/" + MAX_QUESTION;
    };
    const onKey = (event) => {
      if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        submit(input.value);
      }
    };
    const onCancel = () => {
      gate.cancel();
      clearTimer();
      setPending(false);
      status.textContent = "Запрос отменён.";
    };
    form.addEventListener("submit", onSubmit);
    examples.addEventListener("click", onChip);
    input.addEventListener("input", onInput);
    input.addEventListener("keydown", onKey);
    cancel.addEventListener("click", onCancel);

    return {
      ask: (question) => submit(question),
      destroy() {
        if (destroyed) return;
        destroyed = true;
        gate.cancel();
        clearTimer();
        form.removeEventListener("submit", onSubmit);
        examples.removeEventListener("click", onChip);
        input.removeEventListener("input", onInput);
        input.removeEventListener("keydown", onKey);
        cancel.removeEventListener("click", onCancel);
        section.remove();
      },
    };
  }

  // ------------------------------------------------------------ редакторская панель черновика

  function highlighted(text, spans) {
    // Исходный текст с подсветкой цитат: только текстовые узлы и <mark>, без HTML-разбора.
    const pre = el("div", { className: "civic-r09-source" });
    const marks = spans
      .filter((s) => Array.isArray(s.span) && s.span[0] >= 0 && s.span[1] <= text.length && s.span[0] < s.span[1])
      .sort((a, b) => a.span[0] - b.span[0]);
    let pos = 0;
    for (const m of marks) {
      if (m.span[0] < pos) continue;
      pre.append(document.createTextNode(text.slice(pos, m.span[0])));
      pre.append(el("mark", { className: "civic-r09-mark civic-r09-mark--" + m.kind, title: m.label }, text.slice(m.span[0], m.span[1])));
      pos = m.span[1];
    }
    pre.append(document.createTextNode(text.slice(pos)));
    return pre;
  }

  const VALUE_LABELS = {
    kind: { construction: "строительство", roadworks: "дорожные работы", landscaping: "благоустройство", event: "мероприятие" },
    "budget.basis": { planned: "плановая сумма", contract: "сумма по договору", spent: "освоено", unknown: "основание не найдено" },
  };

  function formatValue(field, value) {
    if (value === null || value === undefined) return "нет значения — заполните вручную";
    if (VALUE_LABELS[field] && Object.prototype.hasOwnProperty.call(VALUE_LABELS[field], value)) return VALUE_LABELS[field][value] + " (" + value + ")";
    if (field === "budget.amount_kzt" && typeof value === "number") return value.toLocaleString("ru-RU") + " ₸";
    return String(value);
  }

  function mountDraftReview(options) {
    const opts = options || {};
    const root = opts.root;
    const api = opts.api;
    const onApplyField = typeof opts.onApplyField === "function" ? opts.onApplyField : null;
    if (!root || typeof root.append !== "function") throw new TypeError("mountDraftReview: root is required");
    if (!api || typeof api.request !== "function") throw new TypeError("mountDraftReview: api.request is required");
    const gate = requestGate();
    let destroyed = false;
    let lastText = "";

    const section = el("section", { className: "civic-r09 civic-r09-draft", "aria-label": "Черновик полей из публикации" });
    section.append(el("h3", { className: "civic-r09-title" }, "Предложить поля из текста публикации"));
    section.append(el("p", { className: "civic-r09-hint" },
      "Вставьте текст сами. Ссылка только запоминается — сервер её не открывает. Предложение — черновик: поля переносятся в форму только вручную, публикация — отдельным действием редактора."));
    const form = el("form", { className: "civic-r09-form", novalidate: true });
    const mk = (label, node) => {
      const wrap = el("label", { className: "civic-r09-field" });
      wrap.append(el("span", null, label), node);
      return wrap;
    };
    const text = el("textarea", { className: "civic-r09-input", rows: "6", maxlength: String(MAX_TEXT), required: true });
    const sourceId = el("input", { className: "civic-r09-input", maxlength: "120", value: opts.sourceId || "", placeholder: "src-…" });
    const url = el("input", { className: "civic-r09-input", maxlength: "500", type: "url", placeholder: "https://…" });
    const publisher = el("input", { className: "civic-r09-input", maxlength: "160" });
    const published = el("input", { className: "civic-r09-input", type: "date" });
    const go = el("button", { type: "submit", className: "civic-r09-ask" }, "Предложить поля");
    form.append(mk("Текст публикации", text), mk("ID источника", sourceId), mk("Ссылка (не открывается)", url),
      mk("Издатель", publisher), mk("Дата публикации", published), go);
    const status = el("p", { className: "civic-r09-status", role: "status", "aria-live": "polite" });
    const out = el("div", { className: "civic-r09-draft-out" });
    section.append(form, status, out);
    root.append(section);

    function render(draft) {
      out.replaceChildren();
      out.append(el("p", { className: "civic-r09-banner" },
        "Черновик извлечения из вставленного текста. Это не сообщение городского органа и не опубликованные сведения."));
      const fields = draft && typeof draft.fields === "object" && draft.fields ? draft.fields : {};
      const table = el("table", { className: "civic-r09-table" });
      const thead = el("thead");
      const hr = el("tr");
      for (const h of ["Принять", "Поле", "Предложение", "Цитата", "Как найдено"]) hr.append(el("th", { scope: "col" }, h));
      thead.append(hr);
      const tbody = el("tbody");
      const checks = [];
      const spans = [];
      for (const [field, p] of Object.entries(fields)) {
        if (!p || typeof p !== "object" || !FIELD_LABELS[field]) continue;
        const tr = el("tr", { "data-field": field });
        const cb = el("input", { type: "checkbox", "aria-label": "Принять поле " + FIELD_LABELS[field] });
        if (p.value === null || p.value === undefined) cb.disabled = true;
        checks.push({ cb, field, p });
        const tdc = el("td");
        tdc.append(cb);
        tr.append(tdc, el("td", null, FIELD_LABELS[field]), el("td", { className: p.value == null ? "civic-r09-null" : "" }, formatValue(field, p.value)));
        const q = el("td");
        q.append(el("q", null, typeof p.quote === "string" ? p.quote : ""));
        if (Array.isArray(p.alternatives) && p.alternatives.length) {
          const alts = p.alternatives.filter((a) => a && typeof a.quote === "string").map((a) => "«" + a.quote + "»");
          q.append(el("div", { className: "civic-r09-alts" }, "Другие варианты: " + alts.join("; ")));
        }
        tr.append(q);
        const how = el("td");
        how.append(el("span", null, CONFIDENCE_LABELS[p.confidence_kind] || String(p.confidence_kind || "")));
        if (typeof p.note === "string" && p.note) how.append(el("div", { className: "civic-r09-alts" }, p.note));
        tr.append(how);
        tbody.append(tr);
        spans.push({ span: p.span, kind: p.value == null ? "review" : "field", label: FIELD_LABELS[field] });
      }
      table.append(thead, tbody);
      if (!tbody.childElementCount) out.append(el("p", { className: "civic-r09-note" }, "В тексте не найдено полей для предложения."));
      else out.append(table);
      const ignored = Array.isArray(draft.ignored_instructions) ? draft.ignored_instructions : [];
      if (ignored.length) {
        out.append(el("p", { className: "civic-r09-warn" },
          "В тексте найдены инструкции (" + ignored.length + "). Они не выполнялись и учтены только как текст."));
        for (const r of ignored) spans.push({ span: r.span, kind: "ignored", label: "проигнорированная инструкция" });
      }
      const unassigned = Array.isArray(draft.unassigned_dates) ? draft.unassigned_dates : [];
      if (unassigned.length) {
        out.append(el("p", { className: "civic-r09-note" },
          "Даты без понятной роли (начало/окончание): " + unassigned.map((d) => "«" + d.quote + "»").join(", ") + "."));
      }
      if (lastText) out.append(highlighted(lastText, spans));
      const apply = el("button", { type: "button", className: "civic-r09-ask", disabled: !onApplyField }, "Перенести отмеченные в форму");
      const applied = el("p", { className: "civic-r09-status", role: "status" });
      apply.addEventListener("click", () => {
        if (!onApplyField || destroyed) return;
        let n = 0;
        for (const { cb, field, p } of checks) {
          if (!cb.checked || cb.disabled) continue;
          onApplyField(field, p.value, { quote: p.quote, span: p.span, source_id: p.source_id, confidence_kind: p.confidence_kind });
          n += 1;
        }
        applied.textContent = n ? "Перенесено полей: " + n + ". Проверьте форму и сохраните её сами." : "Не отмечено ни одного поля.";
      });
      out.append(apply, applied);
    }

    const onSubmit = async (event) => {
      event.preventDefault();
      const body = { source_id: sourceId.value.trim(), text: text.value };
      if (url.value.trim()) body.url = url.value.trim();
      if (publisher.value.trim()) body.publisher = publisher.value.trim();
      if (published.value) body.published_on = published.value;
      if (!body.text.trim() || !body.source_id) {
        status.textContent = "Нужны текст публикации и ID источника.";
        return;
      }
      const ticket = gate.start();
      lastText = body.text;
      go.disabled = true;
      status.textContent = "Разбираю текст…";
      out.replaceChildren();
      try {
        const draft = await api.request("POST", "/staff/assistant/extract", body, { signal: ticket.signal, timeoutMs: CLIENT_TIMEOUT_MS });
        if (destroyed || !gate.isCurrent(ticket.id)) return;
        status.textContent = "";
        render(draft || {});
      } catch (error) {
        if (destroyed || !gate.isCurrent(ticket.id)) return;
        if (!(error && error.code === "aborted")) status.textContent = errorMessage(error);
      } finally {
        if (!destroyed && gate.isCurrent(ticket.id)) go.disabled = false;
      }
    };
    form.addEventListener("submit", onSubmit);
    return {
      destroy() {
        if (destroyed) return;
        destroyed = true;
        gate.cancel();
        form.removeEventListener("submit", onSubmit);
        section.remove();
      },
    };
  }

  const existing = global.CivicAssistant && typeof global.CivicAssistant === "object" ? global.CivicAssistant : {};
  global.CivicAssistant = Object.assign(existing, { mount, mountDraftReview, version: "r09-civic-assistant-ui-1" });
})(typeof window !== "undefined" ? window : globalThis);
