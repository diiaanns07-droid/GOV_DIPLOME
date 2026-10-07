/* R06 civic-v1: форма сообщения жителя и очередь модерации.
 *
 * window.CivicFeedback.mount({root, api, objectId, geometry}) -> {destroy}
 * window.CivicFeedback.mountModeration({root, api, map, onOpenObject}) -> {refresh, destroy}
 *
 * api.request(method, path, body) -> Promise<data> предоставляет R01 (CSRF, ошибки).
 * Пути относительные к /api/civic/v1. Недоверенный текст выводится только через
 * textContent; innerHTML не используется. Компонент не трогает document.body,
 * не создаёт карту и снимает свои слушатели/маркеры в destroy().
 */
(function () {
  "use strict";

  var P = "civic-r06";
  // [значение, название, пример — помогает выбрать категорию без знания структуры акимата]
  var CATEGORIES = [
    ["roads", "Дороги", "ямы, разметка, проезд, ограждения"],
    ["sidewalks", "Тротуары и пешеходные пути", "проход, переходы, бордюры, коляски"],
    ["transport_stops", "Остановки транспорта", "павильон, подход, табло"],
    ["lighting", "Освещение", "не горят фонари, тёмный участок"],
    ["landscaping", "Благоустройство и озеленение", "деревья, газоны, скамейки, дворы"],
    ["other", "Другое", "если ничего не подходит"],
  ];
  var CATEGORY_LABEL = {};
  CATEGORIES.forEach(function (c) { CATEGORY_LABEL[c[0]] = c[1]; });
  // Статус обработки на платформе (round 12) — не статус eOtinish/iKOMEK.
  var HANDLING = [
    ["new", "Новое"],
    ["in_review", "В работе"],
    ["answered", "Дан ответ"],
    ["duplicate", "Дубль"],
    ["closed", "Закрыто"],
  ];
  var HANDLING_LABEL = {};
  HANDLING.forEach(function (h) { HANDLING_LABEL[h[0]] = h[1]; });
  var KINDS = [
    ["problem", "Сообщить о проблеме"],
    ["suggestion", "Предложить улучшение"],
  ];
  var KIND_SHORT = { problem: "Проблема", suggestion: "Предложение" };
  var HISTORY_LABELS = {
    submitted: "получено",
    approved: "одобрено",
    rejected: "отклонено",
    published: "опубликовано",
    updated: "публичная версия изменена",
    consent_withdrawn: "автор отозвал согласие",
    status_changed: "статус обработки изменён",
    note: "служебная заметка",
    recategorized: "категория исправлена сотрудником",
  };
  var OBJECT_STATUS = {
    planned: "запланировано", in_progress: "работы идут (по данным источника)",
    completed: "завершено (по данным источника)", cancelled: "отменено", unknown: "статус неизвестен",
  };
  var PUBLICATION = { published: "опубликован", draft: "черновик", archived: "в архиве" };
  var TEXT_MIN = 10;
  var TEXT_MAX = 2000;
  var OFFICIAL_NOTICE =
    "Сообщение на платформе; официальная регистрация не выполняется. " +
    "Для официального обращения используйте eOtinish или единый контакт-центр iKOMEK 109.";
  var PRIVACY_HINT =
    "Не указывайте телефон, ИИН, адрес проживания и имена — для этой формы они не нужны.";
  var QUEUE_TABS = [
    ["new,in_review", "К обработке"],
    ["new", "Новые"],
    ["in_review", "В работе"],
    ["answered", "С ответом"],
    ["duplicate", "Дубли"],
    ["closed", "Закрытые"],
    ["all", "Все"],
  ];
  // Черновик: в памяти страницы и в sessionStorage этой вкладки (переживает перезагрузку и
  // ошибку сети, исчезает при закрытии вкладки и после успешной отправки). Без контактов автора.
  var drafts = new Map();
  var DRAFT_PREFIX = "civic-r06-draft:";

  function storedDraft(key) {
    try {
      var raw = window.sessionStorage && window.sessionStorage.getItem(DRAFT_PREFIX + key);
      var value = raw ? JSON.parse(raw) : null;
      if (!value || typeof value.text !== "string" || typeof value.requestId !== "string") return null;
      return { kind: value.kind === "suggestion" ? "suggestion" : "problem", category: String(value.category || ""),
        text: value.text.slice(0, 2000), consent: value.consent === true || value.consent === false ? value.consent : null,
        requestId: value.requestId.slice(0, 64), confirm: false };
    } catch (e) {
      return null;
    }
  }

  function storeDraft(key, draft) {
    try {
      if (!window.sessionStorage) return;
      if (!draft.text && !draft.category) window.sessionStorage.removeItem(DRAFT_PREFIX + key);
      else window.sessionStorage.setItem(DRAFT_PREFIX + key, JSON.stringify({ kind: draft.kind, category: draft.category,
        text: draft.text, consent: draft.consent, requestId: draft.requestId }));
    } catch (e) { /* хранилище недоступно (приватный режим) — остаётся черновик в памяти */ }
  }

  function dropDraft(key) {
    drafts.delete(key);
    try { if (window.sessionStorage) window.sessionStorage.removeItem(DRAFT_PREFIX + key); } catch (e) { /* нет хранилища */ }
  }
  var uid = 0;

  function nextId(name) {
    uid += 1;
    return P + "-" + name + "-" + uid;
  }

  function el(tag, props, children) {
    var node = document.createElement(tag);
    var key;
    props = props || {};
    for (key in props) {
      if (!Object.prototype.hasOwnProperty.call(props, key)) continue;
      var value = props[key];
      if (value === null || value === undefined || value === false) continue;
      if (key === "text") node.textContent = String(value);
      else if (key === "className") node.className = value;
      else if (key === "dataset") Object.assign(node.dataset, value);
      else if (key in node && key !== "list" && key !== "form") node[key] = value;
      else node.setAttribute(key, value === true ? "" : String(value));
    }
    (children || []).forEach(function (child) {
      if (child === null || child === undefined || child === false) return;
      node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
    });
    return node;
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function formatDate(value) {
    if (!value) return "";
    var date = new Date(value);
    if (isNaN(date.getTime())) return String(value);
    try {
      return date.toLocaleString("ru-RU", { dateStyle: "medium", timeStyle: value.length > 10 ? "short" : undefined });
    } catch (e) {
      return date.toISOString();
    }
  }

  function requestId() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") return window.crypto.randomUUID();
    var bytes = new Uint8Array(16);
    if (window.crypto && window.crypto.getRandomValues) window.crypto.getRandomValues(bytes);
    else for (var i = 0; i < 16; i += 1) bytes[i] = Math.floor(Math.random() * 256);
    return Array.prototype.map.call(bytes, function (b) { return ("0" + b.toString(16)).slice(-2); }).join("");
  }

  // Нормализация ошибок разных обёрток api.request (R01) и собственного fetch-адаптера.
  function errorInfo(err) {
    var source = (err && (err.error || (err.body && err.body.error) || err.data)) || {};
    var status = (err && (err.status || err.statusCode)) || source.status || 0;
    return {
      status: status,
      code: (err && err.code) || source.code || (status ? "http_" + status : "network"),
      message: (err && err.apiMessage) || source.message || (err && err.message) || "",
      fields: (err && err.fields) || source.fields || null,
      canConfirm: Boolean((err && err.can_confirm) || source.can_confirm),
      currentRevision: (err && err.current_revision) || source.current_revision || null,
      previousReceipt: (err && err.previous_receipt) || source.previous_receipt || null,
      allowed: (err && err.allowed) || source.allowed || null,
    };
  }

  function humanError(info, fallback) {
    if (info.status === 0 || info.code === "network")
      return "Нет связи с сервером. Текст сохранён в форме — повторите отправку.";
    if (info.status === 401) return "Сессия истекла или вы вышли. Войдите снова — действие не выполнено.";
    if (info.status === 403) return info.message || "Действие запрещено. Обновите страницу.";
    if (info.status === 413) return "Слишком большой текст.";
    if (info.status === 429) return "Слишком много сообщений подряд. Попробуйте позже — текст сохранён.";
    if (info.status >= 500) return "Сервис временно недоступен. Текст сохранён в форме — повторите позже.";
    return info.message || fallback;
  }

  function receiptError(err, fallback) {
    var info = errorInfo(err);
    if ((info.status === 404 || info.status === 405) && info.code !== "receipt_not_found")
      return "Эта функция пока не подключена в сборке платформы. Номер квитанции сохраните.";
    return humanError(info, fallback);
  }

  function createFetchApi(base, options) {
    base = base || "/api/civic/v1";
    options = options || {};
    return {
      request: function (method, path, body) {
        var headers = { Accept: "application/json" };
        if (body !== undefined && body !== null) headers["Content-Type"] = "application/json";
        var token = typeof options.csrfToken === "function" ? options.csrfToken() : options.csrfToken;
        if (token && method !== "GET") headers["X-CSRF-Token"] = token;
        return fetch(base + path, {
          method: method,
          headers: headers,
          credentials: "same-origin",
          body: body === undefined || body === null ? undefined : JSON.stringify(body),
        }).then(function (response) {
          return response
            .json()
            .catch(function () { return null; })
            .then(function (payload) {
              if (payload && payload.ok === true) return payload.data;
              var error = new Error((payload && payload.error && payload.error.message) || "HTTP " + response.status);
              error.status = response.status;
              error.error = (payload && payload.error) || { code: "http_" + response.status };
              throw error;
            });
        });
      },
    };
  }

  function lifecycle(root) {
    var controller = typeof AbortController === "function" ? new AbortController() : null;
    var listeners = [];
    var state = { destroyed: false };
    state.on = function (node, type, handler) {
      if (controller) node.addEventListener(type, handler, { signal: controller.signal });
      else {
        node.addEventListener(type, handler);
        listeners.push([node, type, handler]);
      }
    };
    state.destroy = function (extra) {
      if (state.destroyed) return;
      state.destroyed = true;
      if (controller) controller.abort();
      listeners.forEach(function (item) { item[0].removeEventListener(item[1], item[2]); });
      if (extra) extra();
      clear(root);
      root.classList.remove(P);
    };
    return state;
  }

  function isPoint(geometry) {
    return Boolean(geometry && geometry.type === "Point" && Array.isArray(geometry.coordinates) &&
      geometry.coordinates.length >= 2 && isFinite(geometry.coordinates[0]) && isFinite(geometry.coordinates[1]));
  }

  function targetKey(objectId, geometry) {
    if (objectId) return "object:" + objectId;
    if (geometry && geometry.coordinates) return "point:" + geometry.coordinates.join(",");
    return "none";
  }

  // ------------------------------------------------------------------ resident
  function mount(options) {
    options = options || {};
    var root = options.root;
    if (!root || !root.appendChild) throw new Error("CivicFeedback.mount: root обязателен");
    var api = options.api || createFetchApi();
    var objectId = options.objectId || null;
    // Место без объекта — только точка [lon, lat]. Геометрию объекта (R03 onFeedback) сервер не ждёт.
    var geometry = isPoint(options.geometry) ? { type: "Point", coordinates: options.geometry.coordinates.slice(0, 2) } : null;
    var life = lifecycle(root);
    var on = life.on;
    var key = targetKey(objectId, geometry);
    var draft = drafts.get(key) || storedDraft(key) || {
      kind: "problem", category: "", text: "", consent: null, requestId: requestId(), confirm: false,
    };
    drafts.set(key, draft);
    function saveDraft() { storeDraft(key, draft); }
    var sending = false;
    var lastReceipt = null;

    clear(root);
    root.classList.add(P);
    var container = el("section", { className: P + "-feedback", "aria-label": "Сообщение жителя" });
    root.appendChild(container);

    var publicSection = objectId ? el("section", { className: P + "-public" }) : null;
    var formSection = el("section", { className: P + "-form-wrap" });
    if (publicSection) container.appendChild(publicSection);
    container.appendChild(formSection);

    // ---- публичные сообщения по объекту
    function renderPublic(items, notice, nextCursor, append) {
      if (!publicSection) return;
      var list = publicSection.querySelector("." + P + "-public-list");
      if (!append || !list) {
        clear(publicSection);
        publicSection.appendChild(el("h3", { className: P + "-title", text: "Сообщения жителей" }));
        publicSection.appendChild(el("p", { className: P + "-notice", text: notice }));
        list = el("ul", { className: P + "-public-list" });
        publicSection.appendChild(list);
      }
      var old = publicSection.querySelector("." + P + "-more");
      if (old) old.remove();
      if (!append && !items.length) {
        list.appendChild(el("li", { className: P + "-empty", text: "Пока нет опубликованных сообщений." }));
      }
      items.forEach(function (item) {
        var reply = item.public_reply
          ? el("div", { className: P + "-reply" }, [
              el("strong", { text: "Ответ модератора платформы: " }),
              el("span", { text: item.public_reply }),
            ])
          : null;
        list.appendChild(
          el("li", { className: P + "-public-item", dataset: { feedbackId: item.id } }, [
            el("div", { className: P + "-meta" }, [
              el("span", { className: P + "-chip", text: item.kind_label }),
              el("span", { className: P + "-chip " + P + "-chip-muted", text: item.category_label }),
              el("time", { dateTime: item.published_at || "", text: formatDate(item.submitted_on) }),
            ]),
            el("p", { className: P + "-text", text: item.text }),
            reply,
            el("small", { className: P + "-muted", text: "Не является официальным обращением." }),
          ])
        );
      });
      if (nextCursor) {
        var more = el("button", { type: "button", className: P + "-link " + P + "-more", text: "Показать ещё" });
        on(more, "click", function () { loadPublic(nextCursor); });
        publicSection.appendChild(more);
      }
    }

    function loadPublic(cursor) {
      if (!publicSection) return;
      var path = "/objects/" + encodeURIComponent(objectId) + "/feedback" + (cursor ? "?cursor=" + encodeURIComponent(cursor) : "");
      api.request("GET", path).then(
        function (data) {
          if (life.destroyed) return;
          renderPublic(data.items || [], data.notice || OFFICIAL_NOTICE, data.next_cursor, Boolean(cursor));
        },
        function () {
          if (life.destroyed) return;
          clear(publicSection);
          publicSection.appendChild(el("h3", { className: P + "-title", text: "Сообщения жителей" }));
          publicSection.appendChild(el("p", { className: P + "-muted", text: "Не удалось загрузить опубликованные сообщения." }));
        }
      );
    }

    // ---- форма
    var ids = { text: nextId("text"), category: nextId("category"), status: nextId("status"), counter: nextId("counter") };
    var form = el("form", { className: P + "-form", noValidate: true });
    var kindSet = el("fieldset", { className: P + "-kinds" }, [el("legend", { text: "Что вы хотите сообщить?" })]);
    var kindName = nextId("kind");
    KINDS.forEach(function (pair) {
      var input = el("input", { type: "radio", name: kindName, value: pair[0], checked: draft.kind === pair[0] });
      on(input, "change", function () { draft.kind = input.value; saveDraft(); });
      kindSet.appendChild(el("label", { className: P + "-choice" }, [input, " " + pair[1]]));
    });

    var category = el("select", { id: ids.category, required: true });
    category.appendChild(el("option", { value: "", text: "Выберите категорию" }));
    CATEGORIES.forEach(function (pair) {
      category.appendChild(el("option", { value: pair[0], text: pair[1] + " — " + pair[2], selected: draft.category === pair[0] }));
    });
    on(category, "change", function () { draft.category = category.value; clearFieldError("category"); saveDraft(); });

    var textarea = el("textarea", {
      id: ids.text, rows: 5, maxLength: TEXT_MAX, required: true,
      placeholder: "Что происходит и где именно? Например: нет прохода вдоль ограждения у остановки.",
      "aria-describedby": ids.counter,
    });
    textarea.value = draft.text;
    var counter = el("small", { id: ids.counter, className: P + "-muted" });
    function updateCounter() { counter.textContent = textarea.value.length + " / " + TEXT_MAX + ". " + PRIVACY_HINT; }
    updateCounter();
    on(textarea, "input", function () { draft.text = textarea.value; updateCounter(); clearFieldError("text"); saveDraft(); });

    var consentSet = el("fieldset", { className: P + "-consent" }, [
      el("legend", { text: "Публикация текста" }),
    ]);
    var consentName = nextId("consent");
    [
      [true, "Можно опубликовать текст на карте после проверки модератором платформы"],
      [false, "Не публиковать: текст увидят только модераторы платформы"],
    ].forEach(function (pair) {
      var input = el("input", { type: "radio", name: consentName, value: String(pair[0]), checked: draft.consent === pair[0] });
      on(input, "change", function () { draft.consent = pair[0]; clearFieldError("consent_public"); saveDraft(); });
      consentSet.appendChild(el("label", { className: P + "-choice" }, [input, " " + pair[1]]));
    });

    var place = objectId
      ? el("p", { className: P + "-muted", text: "Сообщение будет связано с выбранным объектом." })
      : geometry && geometry.coordinates
        ? el("p", { className: P + "-muted", text: "Место на карте: " + Number(geometry.coordinates[1]).toFixed(5) + ", " + Number(geometry.coordinates[0]).toFixed(5) })
        : el("p", { className: P + "-error", text: "Выберите объект или точку на карте, чтобы отправить сообщение." });

    var status = el("div", { id: ids.status, className: P + "-status", role: "status", "aria-live": "polite" });
    var submit = el("button", { type: "submit", className: P + "-primary", text: "Отправить сообщение" });
    var fieldErrors = {};

    function fieldError(name, message) {
      var anchor = { text: textarea, category: category, consent_public: consentSet, location: place, geometry: place, object_id: place }[name];
      if (!anchor) return;
      clearFieldError(name);
      var node = el("small", { className: P + "-field-error", text: message });
      anchor.insertAdjacentElement("afterend", node);
      fieldErrors[name] = node;
      if (anchor.setAttribute) anchor.setAttribute("aria-invalid", "true");
    }

    function clearFieldError(name) {
      if (fieldErrors[name]) {
        fieldErrors[name].remove();
        delete fieldErrors[name];
      }
      var anchor = { text: textarea, category: category, consent_public: consentSet }[name];
      if (anchor) anchor.removeAttribute("aria-invalid");
    }

    function setStatus(message, kind, action) {
      clear(status);
      status.className = P + "-status" + (kind ? " " + P + "-status-" + kind : "");
      if (message) status.appendChild(el("span", { text: message }));
      if (action) status.appendChild(action);
    }

    form.appendChild(el("h3", { className: P + "-title", text: objectId ? "Написать о проблеме или предложении" : "Сообщение о месте на карте" }));
    form.appendChild(el("p", { className: P + "-official", text: OFFICIAL_NOTICE }));
    form.appendChild(kindSet);
    form.appendChild(el("label", { className: P + "-label", htmlFor: ids.category, text: "Категория" }));
    form.appendChild(category);
    form.appendChild(el("label", { className: P + "-label", htmlFor: ids.text, text: "Текст сообщения" }));
    form.appendChild(textarea);
    form.appendChild(counter);
    form.appendChild(consentSet);
    form.appendChild(place);
    form.appendChild(el("small", { className: P + "-muted " + P + "-draft-note",
      text: "Черновик хранится только в этой вкладке браузера до отправки: при ошибке сети текст не потеряется." }));
    form.appendChild(status);
    form.appendChild(submit);
    formSection.appendChild(form);

    function localErrors() {
      var errors = {};
      var text = textarea.value.trim();
      if (text.length < TEXT_MIN) errors.text = "Опишите подробнее: не меньше " + TEXT_MIN + " символов.";
      if (text.length > TEXT_MAX) errors.text = "Не больше " + TEXT_MAX + " символов.";
      if (!category.value) errors.category = "Выберите категорию.";
      if (draft.consent !== true && draft.consent !== false) errors.consent_public = "Выберите, можно ли публиковать текст.";
      if (!objectId && !(geometry && geometry.coordinates)) errors.location = "Нет объекта или места.";
      return errors;
    }

    function send() {
      if (sending || life.destroyed) return;
      var errors = localErrors();
      Object.keys(fieldErrors).forEach(clearFieldError);
      if (Object.keys(errors).length) {
        Object.keys(errors).forEach(function (name) { fieldError(name, errors[name]); });
        setStatus("Проверьте выделенные поля.", "error");
        return;
      }
      sending = true;
      submit.disabled = true;
      form.setAttribute("aria-busy", "true");
      setStatus("Отправляем…", "info");
      var body = {
        object_id: objectId,
        geometry: objectId ? null : geometry,
        kind: draft.kind,
        category: category.value,
        text: textarea.value,
        consent_public: draft.consent,
        client_request_id: draft.requestId,
      };
      if (draft.confirm) body.confirm_duplicate = true;
      api.request("POST", "/feedback", body).then(
        function (receipt) {
          sending = false;
          if (life.destroyed) return;
          dropDraft(key);
          showReceipt(receipt);
        },
        function (err) {
          sending = false;
          if (life.destroyed) return;
          submit.disabled = false;
          form.removeAttribute("aria-busy");
          var info = errorInfo(err);
          if (info.code === "duplicate_warning") {
            var confirm = el("button", { type: "button", className: P + "-link", text: "Всё равно отправить" });
            on(confirm, "click", function () { draft.confirm = true; send(); });
            setStatus(info.message || "Такое сообщение уже отправлено с этого устройства.", "warning", confirm);
            return;
          }
          if (info.code === "request_id_conflict") {
            // Прежняя версия уже сохранена (ответ мог потеряться). Не создаём копию молча.
            var prev = info.previousReceipt;
            var resend = el("button", { type: "button", className: P + "-link", text: "Отправить изменённый текст отдельным сообщением" });
            on(resend, "click", function () { draft.requestId = requestId(); saveDraft(); send(); });
            setStatus("Предыдущая версия уже сохранена" + (prev && prev.receipt_id ? " (квитанция " + prev.receipt_id + ")" : "") + ". ", "warning", resend);
            return;
          }
          if (info.fields) Object.keys(info.fields).forEach(function (name) { fieldError(name, info.fields[name]); });
          setStatus(humanError(info, "Не удалось отправить сообщение. Текст сохранён в форме."), "error");
        }
      );
    }

    on(form, "submit", function (event) { event.preventDefault(); send(); });

    function showReceipt(receipt) {
      lastReceipt = receipt;
      clear(formSection);
      var receiptBox = el("div", { className: P + "-receipt", role: "status", tabIndex: -1 });
      var receiptStatus = el("p", { className: P + "-receipt-status", text: "Статус: " + (receipt.moderation_label || "ожидает проверки модератором платформы") });
      var actionStatus = el("div", { className: P + "-status", role: "status", "aria-live": "polite" });
      receiptBox.appendChild(el("h3", { className: P + "-title", text: "Сообщение сохранено на платформе" }));
      receiptBox.appendChild(el("p", {}, [
        "Номер квитанции: ",
        el("code", { className: P + "-receipt-id", text: receipt.receipt_id }),
      ]));
      receiptBox.appendChild(el("p", { className: P + "-muted", text: "Сохраните номер: по нему можно проверить статус или отозвать согласие на публикацию." }));
      receiptBox.appendChild(receiptStatus);
      receiptBox.appendChild(el("p", { className: P + "-official", text: receipt.notice || OFFICIAL_NOTICE }));
      (receipt.warnings || []).forEach(function (warning) {
        receiptBox.appendChild(el("p", { className: P + "-status " + P + "-status-warning", text: warning }));
      });
      var actions = el("div", { className: P + "-actions" });
      var check = el("button", { type: "button", className: P + "-link", text: "Проверить статус" });
      on(check, "click", function () {
        check.disabled = true;
        api.request("POST", "/feedback/receipt", { receipt_id: receipt.receipt_id }).then(
          function (data) {
            check.disabled = false;
            if (life.destroyed) return;
            receiptStatus.textContent = "Статус: " + data.moderation_label + (data.handling_label ? " · обработка: " + data.handling_label : "") +
              (data.is_public ? " · текст опубликован" : "");
            clear(actionStatus);
            if (data.public_reply) {
              actionStatus.appendChild(el("span", { text: "Ответ платформы: " }));
              actionStatus.appendChild(el("span", { text: data.public_reply }));
            }
          },
          function (err) {
            check.disabled = false;
            if (!life.destroyed) actionStatus.textContent = receiptError(err, "Не удалось проверить статус.");
          }
        );
      });
      actions.appendChild(check);
      if (receipt.consent_public) {
        var withdraw = el("button", { type: "button", className: P + "-link", text: "Отозвать согласие на публикацию" });
        on(withdraw, "click", function () {
          withdraw.disabled = true;
          api.request("POST", "/feedback/withdraw-consent", { receipt_id: receipt.receipt_id }).then(
            function () {
              if (life.destroyed) return;
              withdraw.remove();
              actionStatus.textContent = "Согласие отозвано: текст не будет показан публично.";
              loadPublic();
            },
            function (err) {
              withdraw.disabled = false;
              if (!life.destroyed) actionStatus.textContent = receiptError(err, "Не удалось отозвать согласие.");
            }
          );
        });
        actions.appendChild(withdraw);
      }
      var again = el("button", { type: "button", className: P + "-link", text: "Написать ещё одно сообщение" });
      on(again, "click", function () { instance.destroy(); Object.assign(instance, mount(options)); });
      actions.appendChild(again);
      receiptBox.appendChild(actions);
      receiptBox.appendChild(actionStatus);
      formSection.appendChild(receiptBox);
      if (receiptBox.focus) receiptBox.focus();
    }

    loadPublic();
    var instance = {
      destroy: function () { life.destroy(); },
      // Для R01/R10: последний receipt без текста сообщения.
      lastReceipt: function () { return lastReceipt; },
    };
    return instance;
  }

  // ---------------------------------------------------------------- moderation
  function mountModeration(options) {
    options = options || {};
    var root = options.root;
    if (!root || !root.appendChild) throw new Error("CivicFeedback.mountModeration: root обязателен");
    var api = options.api || createFetchApi();
    var map = options.map || null;
    var onOpenObject = typeof options.onOpenObject === "function" ? options.onOpenObject : null;
    var marker = null;
    var life = lifecycle(root);
    var on = life.on;
    var filters = { status: "new,in_review", moderation: "", category: "", consent: "", q: "", order: "" };
    var selectedId = null;
    var loadToken = 0;
    var searchTimer = null;
    var cached = {};

    clear(root);
    root.classList.add(P);
    var container = el("section", { className: P + "-moderation", "aria-label": "Сообщения жителей — обработка" });
    var header = el("div", { className: P + "-mod-header" }, [
      el("h3", { className: P + "-title", text: "Сообщения жителей — обработка на платформе" }),
      el("p", { className: P + "-muted", text: "Статусы описывают работу сотрудников этой платформы. Они не регистрируют официальное обращение (eOtinish/iKOMEK) и не означают начала работ." }),
    ]);
    var tabs = el("div", { className: P + "-tabs", role: "tablist" });
    function select_(label, pairs, value) {
      var node = el("select", { "aria-label": label });
      pairs.forEach(function (pair) { node.appendChild(el("option", { value: pair[0], text: pair[1], selected: pair[0] === value })); });
      return node;
    }
    var publicationFilter = select_("Публикация", [["", "Публикация: любая"], ["pending", "Ждут решения о публикации"],
      ["approved", "Одобрены"], ["rejected", "Отклонены"]], "");
    var categoryFilter = select_("Категория", [["", "Все категории"]].concat(CATEGORIES.map(function (c) { return [c[0], c[1]]; })), "");
    var consentFilter = select_("Согласие на публикацию", [["", "Любое согласие"], ["true", "Разрешена публикация"], ["false", "Без публикации"]], "");
    var orderFilter = select_("Порядок", [["", "Порядок: по умолчанию"], ["oldest", "Сначала старые"], ["newest", "Сначала новые"]], "");
    var search = el("input", { type: "search", maxLength: 100, placeholder: "Поиск по тексту или #номеру", "aria-label": "Поиск сообщений" });
    var listStatus = el("div", { className: P + "-status", role: "status", "aria-live": "polite" });
    var list = el("ul", { className: P + "-queue" });
    var detail = el("div", { className: P + "-detail", "aria-live": "polite" });
    container.appendChild(header);
    container.appendChild(tabs);
    container.appendChild(el("div", { className: P + "-filters" }, [search, publicationFilter, categoryFilter, consentFilter, orderFilter]));
    container.appendChild(listStatus);
    container.appendChild(el("div", { className: P + "-mod-body" }, [list, detail]));
    root.appendChild(container);

    on(publicationFilter, "change", function () { filters.moderation = publicationFilter.value; refresh(); });
    on(categoryFilter, "change", function () { filters.category = categoryFilter.value; refresh(); });
    on(consentFilter, "change", function () { filters.consent = consentFilter.value; refresh(); });
    on(orderFilter, "change", function () { filters.order = orderFilter.value; refresh(); });
    on(search, "input", function () {
      if (searchTimer) clearTimeout(searchTimer);
      searchTimer = setTimeout(function () { searchTimer = null; filters.q = search.value.trim(); refresh(); }, 300);
    });

    function renderTabs(counts) {
      clear(tabs);
      QUEUE_TABS.forEach(function (pair) {
        var count = "";
        if (counts && pair[0] !== "all") {
          count = " (" + pair[0].split(",").reduce(function (sum, k) { return sum + (counts[k] || 0); }, 0) + ")";
        }
        var button = el("button", {
          type: "button", role: "tab", className: P + "-tab",
          "aria-selected": String(filters.status === pair[0]), text: pair[1] + count,
        });
        on(button, "click", function () { filters.status = pair[0]; refresh(); });
        tabs.appendChild(button);
      });
    }

    function removeMarker() {
      if (marker && marker.remove) marker.remove();
      marker = null;
    }

    function staffError(err, fallback) {
      var info = errorInfo(err);
      if (info.status === 401) return "Сессия редактора истекла или закрыта. Войдите снова — действие не выполнено.";
      if (info.status === 403) return info.message || "Недостаточно прав или не пройдена проверка CSRF.";
      return humanError(info, fallback);
    }

    function refresh() {
      var token = (loadToken += 1);
      var query = ["status=" + encodeURIComponent(filters.status), "moderation=" + encodeURIComponent(filters.moderation || "all")];
      ["category", "consent", "q", "order"].forEach(function (name) {
        if (filters[name]) query.push(name + "=" + encodeURIComponent(filters[name]));
      });
      listStatus.textContent = "Загрузка…";
      return api.request("GET", "/staff/feedback?" + query.join("&")).then(
        function (data) {
          if (life.destroyed || token !== loadToken) return;
          listStatus.textContent = "";
          renderTabs(data.handling_counts || null);
          renderList(data.items || []);
        },
        function (err) {
          if (life.destroyed || token !== loadToken) return;
          renderTabs(null);
          clear(list);
          listStatus.textContent = staffError(err, "Не удалось загрузить очередь.");
        }
      );
    }

    function renderList(items) {
      clear(list);
      if (!items.length) {
        list.appendChild(el("li", { className: P + "-empty", text: "Нет сообщений в этом фильтре." }));
        return;
      }
      cached = {};
      items.forEach(function (item) {
        cached[item.id] = item;
        var flags = [];
        var hints = item.personal_data_hints || [];
        if (hints.some(function (h) { return h.type !== "url"; })) flags.push("возможны контакты");
        else if (hints.length) flags.push("есть ссылка");
        if (!item.consent_public) flags.push("без публикации");
        if (item.similar_count) flags.push("похожих: " + item.similar_count);
        if (item.antispam && item.antispam.same_sender_24h > 2) flags.push("частые отправки");
        var button = el("button", {
          type: "button", className: P + "-queue-item", "aria-pressed": String(item.id === selectedId),
          dataset: { feedbackId: item.id },
        }, [
          el("span", { className: P + "-meta" }, [
            el("span", { className: P + "-chip " + P + "-handling-" + (item.handling_status || "new"), text: HANDLING_LABEL[item.handling_status] || "Новое" }),
            el("span", { className: P + "-chip", text: KIND_SHORT[item.kind] || item.kind }),
            el("span", { className: P + "-chip " + P + "-chip-muted", text: item.effective_category_label || item.category_label }),
            el("span", { className: P + "-muted", text: "#" + item.id + " · " + formatDate(item.created_at) }),
          ]),
          el("span", { className: P + "-excerpt", text: item.text }),
          el("span", { className: P + "-muted", text: (item.object_id ? "Объект " + item.object_id : "Место на карте") + " · " + (item.moderation_label || "") + (flags.length ? " · " + flags.join(" · ") : "") }),
        ]);
        on(button, "click", function () {
          select(item.id);
          // В одной колонке карточка ниже списка — показать её.
          if (detail.scrollIntoView && detail.getBoundingClientRect().top > list.getBoundingClientRect().bottom - 1)
            detail.scrollIntoView({ block: "start", behavior: "smooth" });
        });
        list.appendChild(el("li", {}, [button]));
      });
    }

    function select(id) {
      selectedId = id;
      Array.prototype.forEach.call(list.querySelectorAll("." + P + "-queue-item"), function (node) {
        node.setAttribute("aria-pressed", String(node.dataset.feedbackId === id));
      });
      clear(detail);
      detail.appendChild(el("p", { className: P + "-muted", text: "Загрузка сообщения…" }));
      return api.request("GET", "/staff/feedback/" + encodeURIComponent(id)).then(
        function (data) { if (!life.destroyed && selectedId === id) renderDetail(data); },
        function (err) {
          if (life.destroyed) return;
          var info = errorInfo(err);
          // Шлюз без маршрута GET /staff/feedback/{id}: решение возможно по данным очереди.
          if ((info.status === 404 || info.status === 405) && info.code !== "feedback_not_found" && cached[id]) {
            renderDetail({ item: cached[id], history: null, object: null, similar: null, degraded: true });
            return;
          }
          clear(detail);
          detail.appendChild(el("p", { className: P + "-error", text: staffError(err, "Не удалось открыть сообщение.") }));
        }
      );
    }

    function codePoints(value) { return Array.from(value || ""); }

    // Подсказки сервера даны в позициях символов Python (code points).
    function redactHints(value, hints) {
      var chars = codePoints(value);
      var out = [];
      var cursor = 0;
      hints.slice().sort(function (a, b) { return a.start - b.start; }).forEach(function (hint) {
        if (hint.start < cursor || hint.type === "url") return;
        out.push(chars.slice(cursor, hint.start).join(""));
        out.push("[скрыто]");
        cursor = hint.end;
      });
      out.push(chars.slice(cursor).join(""));
      return out.join("");
    }

    // Общая отправка действия сотрудника: защита от двойного клика, 409, ошибки полей.
    function submitAction(form, button, status, item, body, done) {
      if (form.dataset.busy === "1") return;
      form.dataset.busy = "1";
      button.disabled = true;
      status.textContent = "Сохраняем…";
      api.request("POST", "/staff/feedback/" + encodeURIComponent(item.id) + "/moderate", body).then(
        function () {
          form.dataset.busy = "";
          if (life.destroyed) return;
          refresh();
          select(item.id).then(function () { if (done) done(); });
        },
        function (err) {
          form.dataset.busy = "";
          button.disabled = false;
          if (life.destroyed) return;
          var info = errorInfo(err);
          if (info.status === 409) {
            status.textContent = "Сообщение уже изменено другим действием. Карточка обновлена — проверьте и повторите.";
            select(item.id);
            return;
          }
          var extra = info.fields ? " " + Object.keys(info.fields).map(function (k) { return info.fields[k]; }).join(" ") : "";
          status.textContent = staffError(err, "Не удалось сохранить.") + extra;
        }
      );
    }

    function renderDetail(data) {
      var item = data.item;
      var object = data.object;
      clear(detail);
      removeMarker();
      var consentText = item.consent_withdrawn_at
        ? "Согласие на публикацию отозвано автором " + formatDate(item.consent_withdrawn_at)
        : item.consent_public ? "Автор разрешил публикацию текста после проверки" : "Автор НЕ разрешил публиковать текст";
      detail.appendChild(el("h4", { text: "Сообщение #" + item.id + " · " + item.moderation_label }));
      detail.appendChild(el("p", { className: P + "-handling-line" }, [
        el("span", { className: P + "-chip " + P + "-handling-" + (item.handling_status || "new"), text: HANDLING_LABEL[item.handling_status] || "Новое" }),
        el("span", { className: P + "-muted", text: " " + (item.handling_label || "") + (item.handled_by ? " · " + item.handled_by + ", " + formatDate(item.handled_at) : "") }),
      ]));
      detail.appendChild(el("p", { className: P + "-muted", text: "Ревизия " + item.revision + " · получено " + formatDate(item.created_at) + " · категория жителя: " + (CATEGORY_LABEL[item.category] || item.category) + (item.staff_category ? " → сотрудник: " + (CATEGORY_LABEL[item.staff_category] || item.staff_category) : "") }));
      if (data.degraded) {
        detail.appendChild(el("p", { className: P + "-warning-text", text: "Карточка собрана из очереди: журнал, похожие сообщения и сведения об объекте недоступны в этой сборке (нет маршрута GET /staff/feedback/{id})." }));
      }
      detail.appendChild(el("p", { className: item.consent_public && !item.consent_withdrawn_at ? P + "-ok" : P + "-warning-text", text: consentText }));
      detail.appendChild(el("div", { className: P + "-private" }, [
        el("small", { text: "Исходный текст — только для сотрудников платформы" }),
        el("p", { className: P + "-text", text: item.text }),
      ]));

      // Объект рядом с сообщением
      var objectBox = el("div", { className: P + "-object" });
      if (object && object.available) {
        objectBox.appendChild(el("strong", { text: object.title || object.id }));
        objectBox.appendChild(el("span", { className: P + "-muted", text: " · " + (OBJECT_STATUS[object.status] || OBJECT_STATUS.unknown) + " · " + (PUBLICATION[object.publication] || object.publication || "") }));
        if (object.evidence_type === "synthetic") objectBox.appendChild(el("span", { className: P + "-chip " + P + "-chip-warn", text: "синтетические данные" }));
      } else if (item.object_id) {
        objectBox.appendChild(el("span", { className: P + "-warning-text", text: "Объект " + item.object_id + " сейчас недоступен" }));
      } else if (item.geometry) {
        objectBox.appendChild(el("span", { text: "Место: " + item.geometry.coordinates[1].toFixed(5) + ", " + item.geometry.coordinates[0].toFixed(5) }));
      }
      var showButton = el("button", { type: "button", className: P + "-link", text: "Показать на карте" });
      on(showButton, "click", function () {
        if (onOpenObject && item.object_id) onOpenObject(item.object_id);
        var coords = item.geometry && item.geometry.coordinates;
        if (!coords && object && object.geometry && object.geometry.type === "Point") coords = object.geometry.coordinates;
        if (map && coords && typeof map.flyTo === "function") map.flyTo({ center: coords, zoom: Math.max(map.getZoom ? map.getZoom() : 15, 15) });
      });
      if (onOpenObject || map) objectBox.appendChild(showButton);
      detail.appendChild(objectBox);
      if (map && item.geometry && window.maplibregl && window.maplibregl.Marker) {
        var markerNode = el("div", { className: P + "-marker", title: "Место из сообщения #" + item.id });
        marker = new window.maplibregl.Marker({ element: markerNode }).setLngLat(item.geometry.coordinates).addTo(map);
      }

      if (item.personal_data_hints && item.personal_data_hints.length) {
        detail.appendChild(el("p", { className: P + "-warning-text", text: "Возможные персональные данные: " + item.personal_data_hints.map(function (h) { return h.label; }).join(", ") + ". Автоматический поиск неполный — проверьте имена и адреса вручную." }));
      }
      if (data.duplicate_of) {
        var openOriginal = el("button", { type: "button", className: P + "-link", text: "Исходное сообщение #" + data.duplicate_of.id });
        on(openOriginal, "click", function () { select(data.duplicate_of.id); });
        detail.appendChild(el("p", { className: P + "-muted" }, ["Отмечено как дубль. ", openOriginal, " — " + data.duplicate_of.handling_label]));
      }
      if (data.duplicates && data.duplicates.length) {
        var dupList = el("ul", { className: P + "-similar" });
        data.duplicates.forEach(function (d) {
          var open = el("button", { type: "button", className: P + "-link", text: "#" + d.id });
          on(open, "click", function () { select(d.id); });
          dupList.appendChild(el("li", {}, [open, el("span", { className: P + "-muted", text: " " + d.excerpt })]));
        });
        detail.appendChild(el("details", { open: true }, [el("summary", { text: "Связанные дубли: " + data.duplicates.length }), dupList]));
      }

      var forms = {};
      var clf = item.classifier || {};
      var clfBox = el("div", { className: P + "-classifier" });
      if (clf.suggestion) {
        var sug = clf.suggestion;
        var scoreText = sug.score !== null && sug.score !== undefined
          ? "; оценка модели " + Number(sug.score).toFixed(2) + " (" + (sug.score_kind || "некалиброванная") + ", не вероятность)" : "";
        clfBox.appendChild(el("span", { className: P + "-muted", text: "Подсказка модели " + (sug.model_version || "(версия неизвестна)") + ": «" + sug.label_text + "»" + scoreText + ". Решает сотрудник; категорию жителя модель не меняет." }));
        if (sug.label !== (item.staff_category || item.category)) {
          var useHint = el("button", { type: "button", className: P + "-link", text: "Подставить в исправление категории" });
          on(useHint, "click", function () { if (forms.recat) forms.recat.prefill(sug.label); });
          clfBox.appendChild(useHint);
        }
      } else {
        clfBox.appendChild(el("span", { className: P + "-muted", text: "Подсказка модели: " + ({ unavailable: "модель не подключена", error: "ошибка модели", timeout: "модель не ответила", invalid: "некорректный ответ модели" }[clf.status] || "нет") + ". Сообщение сохранено без неё." }));
      }
      detail.appendChild(clfBox);
      if (data.similar && data.similar.length) {
        var similarList = el("ul", { className: P + "-similar" });
        data.similar.forEach(function (s) {
          var open = el("button", { type: "button", className: P + "-link", text: "#" + s.id + " (общих слов: " + Number(s.score).toFixed(2) + (s.exact_text ? ", тот же текст" : "") + ")" });
          on(open, "click", function () { select(s.id); });
          var mark = el("button", { type: "button", className: P + "-link", text: "Отметить текущее как дубль #" + s.id });
          on(mark, "click", function () { if (forms.handling) forms.handling.prefillDuplicate(s.id); });
          var row = [open, el("span", { className: P + "-muted", text: " " + s.excerpt })];
          if (item.handling_next && item.handling_next.indexOf("duplicate") >= 0 && s.handling_status !== "duplicate") row.push(mark);
          similarList.appendChild(el("li", {}, row));
        });
        detail.appendChild(el("details", { open: true }, [el("summary", { text: "Похожие сообщения — подсказка, система их не объединяет" }), similarList]));
      }

      if (!data.degraded) {
        forms.handling = renderHandlingForm(item);
        detail.appendChild(forms.handling.node);
      }
      detail.appendChild(renderDecisionForm(item));
      if (!data.degraded) {
        forms.recat = renderRecategorizeForm(item);
        detail.appendChild(forms.recat.node);
        detail.appendChild(renderNoteForm(item));
      }

      if (!data.history) return;
      var history = el("ol", { className: P + "-history" });
      var notes = 0;
      data.history.forEach(function (h) {
        if (h.action === "note") notes += 1;
        history.appendChild(el("li", { className: h.action === "note" ? P + "-history-note" : null }, [
          el("span", { text: formatDate(h.at) + " · " + (HISTORY_LABELS[h.action] || h.action) + " · ревизия " + h.revision + (h.actor ? " · " + h.actor : "") }),
          h.reason ? el("span", { className: P + "-muted", text: " — " + h.reason }) : null,
          h.is_public ? el("span", { className: P + "-chip", text: "публично" }) : null,
        ]));
      });
      detail.appendChild(el("details", { open: notes > 0 }, [el("summary", { text: "Журнал действий и служебные заметки" + (notes ? " (заметок: " + notes + ")" : "") }), history]));
    }

    function renderHandlingForm(item) {
      var form = el("form", { className: P + "-handling", noValidate: true });
      var next = item.handling_next || [];
      var statusId = nextId("handling");
      var statusSelect = el("select", { id: statusId });
      statusSelect.appendChild(el("option", { value: "", text: "Выберите новый статус" }));
      next.forEach(function (key) { statusSelect.appendChild(el("option", { value: key, text: HANDLING_LABEL[key] || key })); });
      if (item.handling_status === "answered") statusSelect.appendChild(el("option", { value: "answered", text: "Дан ответ — изменить текст ответа" }));
      var dupId = nextId("dup");
      var dup = el("input", { id: dupId, type: "text", inputMode: "numeric", maxLength: 12, placeholder: "номер, например 12" });
      var dupWrap = el("div", { className: P + "-dup-wrap", hidden: true }, [
        el("label", { className: P + "-label", htmlFor: dupId, text: "Номер исходного сообщения" }), dup,
      ]);
      var replyId = nextId("handling-reply");
      var reply = el("textarea", { id: replyId, rows: 3, maxLength: 2000, placeholder: "Ответ платформы. Не обещайте сроки и работы, которые не подтверждены." });
      reply.value = item.public_reply || "";
      var reasonId = nextId("handling-reason");
      var reason = el("textarea", { id: reasonId, rows: 2, maxLength: 500, placeholder: "Обоснование — видно только сотрудникам" });
      var status = el("div", { className: P + "-status", role: "status", "aria-live": "polite" });
      var submit = el("button", { type: "submit", className: P + "-primary", text: "Сохранить статус" });
      on(statusSelect, "change", function () { dupWrap.hidden = statusSelect.value !== "duplicate"; });
      form.appendChild(el("fieldset", {}, [
        el("legend", { text: "Обработка на платформе" }),
        el("label", { className: P + "-label", htmlFor: statusId, text: "Новый статус (сейчас: " + (HANDLING_LABEL[item.handling_status] || "Новое") + ")" }),
        statusSelect, dupWrap,
        el("label", { className: P + "-label", htmlFor: replyId, text: item.consent_public && !item.consent_withdrawn_at && item.moderation === "approved" ? "Ответ платформы (виден публично и автору по квитанции)" : "Ответ платформы (виден автору по квитанции; публично — только после одобрения)" }),
        reply,
        el("label", { className: P + "-label", htmlFor: reasonId, text: "Обоснование (служебно)" }),
        reason, status, submit,
      ]));
      on(form, "submit", function (event) {
        event.preventDefault();
        if (!statusSelect.value) { status.textContent = "Выберите статус."; return; }
        if (reason.value.trim().length < 3) { status.textContent = "Укажите обоснование."; return; }
        if (statusSelect.value === "answered" && !reply.value.trim()) { status.textContent = "Для статуса «Дан ответ» напишите ответ платформы."; return; }
        if (statusSelect.value === "duplicate" && !/^\d+$/.test(dup.value.trim())) { status.textContent = "Укажите номер исходного сообщения."; return; }
        var body = { expected_revision: item.revision, action: "status", status: statusSelect.value, reason: reason.value };
        if (reply.value.trim() !== (item.public_reply || "").trim()) body.public_reply = reply.value.trim() ? reply.value : null;
        if (statusSelect.value === "duplicate") body.duplicate_of = dup.value.trim();
        submitAction(form, submit, status, item, body);
      });
      return {
        node: form,
        prefillDuplicate: function (id) {
          statusSelect.value = "duplicate";
          dupWrap.hidden = false;
          dup.value = String(id);
          if (!reason.value) reason.value = "Тот же вопрос, что и в сообщении #" + id;
          if (form.scrollIntoView) form.scrollIntoView({ block: "nearest" });
        },
      };
    }

    function renderRecategorizeForm(item) {
      var form = el("form", { className: P + "-recat", noValidate: true });
      var current = item.staff_category || item.category;
      var catId = nextId("recat");
      var cat = el("select", { id: catId });
      CATEGORIES.forEach(function (c) { cat.appendChild(el("option", { value: c[0], text: c[1], selected: c[0] === current })); });
      var reason = el("input", { type: "text", maxLength: 500, placeholder: "Почему категория другая", "aria-label": "Обоснование смены категории" });
      var status = el("div", { className: P + "-status", role: "status", "aria-live": "polite" });
      var submit = el("button", { type: "submit", className: P + "-link", text: "Исправить категорию" });
      form.appendChild(el("details", {}, [
        el("summary", { text: "Категория: " + (CATEGORY_LABEL[current] || current) + (item.staff_category ? " (исправлена сотрудником)" : " (как указал житель)") }),
        el("label", { className: P + "-label", htmlFor: catId, text: "Категория по оценке сотрудника (категория жителя сохраняется в истории)" }),
        cat, reason, submit, status,
      ]));
      on(form, "submit", function (event) {
        event.preventDefault();
        if (cat.value === current) { status.textContent = "Категория не изменилась."; return; }
        if (reason.value.trim().length < 3) { status.textContent = "Укажите обоснование."; return; }
        submitAction(form, submit, status, item, { expected_revision: item.revision, action: "recategorize", category: cat.value, reason: reason.value });
      });
      return {
        node: form,
        prefill: function (label) {
          form.querySelector("details").open = true;
          cat.value = label;
          if (!reason.value) reason.value = "Согласен с подсказкой модели после проверки текста";
          reason.focus();
        },
      };
    }

    function renderNoteForm(item) {
      var form = el("form", { className: P + "-note", noValidate: true });
      var noteId = nextId("note");
      var note = el("textarea", { id: noteId, rows: 2, maxLength: 1000, placeholder: "Служебная заметка: видна только сотрудникам, не публикуется и не отправляется автору" });
      var status = el("div", { className: P + "-status", role: "status", "aria-live": "polite" });
      var submit = el("button", { type: "submit", className: P + "-link", text: "Добавить заметку" });
      form.appendChild(el("label", { className: P + "-label", htmlFor: noteId, text: "Служебная заметка" }));
      form.appendChild(note);
      form.appendChild(submit);
      form.appendChild(status);
      on(form, "submit", function (event) {
        event.preventDefault();
        if (!note.value.trim()) { status.textContent = "Заметка пустая."; return; }
        submitAction(form, submit, status, item, { action: "note", internal_note: note.value });
      });
      return form;
    }

    function renderDecisionForm(item) {
      var form = el("form", { className: P + "-decision", noValidate: true });
      var actionName = nextId("action");
      var approve = el("input", { type: "radio", name: actionName, value: "approve", checked: item.moderation !== "rejected" });
      var reject = el("input", { type: "radio", name: actionName, value: "reject", checked: item.moderation === "rejected" });
      var reasonId = nextId("reason");
      var reason = el("textarea", { id: reasonId, rows: 2, maxLength: 500, required: true, placeholder: "Причина решения — видна только сотрудникам" });
      var canPublish = item.consent_public && !item.consent_withdrawn_at;
      var publicTextId = nextId("public-text");
      var publicText = el("textarea", { id: publicTextId, rows: 4, maxLength: 2000 });
      publicText.value = item.public_text || item.text;
      var replyId = nextId("reply");
      var reply = el("textarea", { id: replyId, rows: 3, maxLength: 2000, placeholder: "Необязательно. Не обещайте сроки и работы, которые не подтверждены." });
      reply.value = item.public_reply || "";
      var status = el("div", { className: P + "-status", role: "status", "aria-live": "polite" });
      var submit = el("button", { type: "submit", className: P + "-primary", text: "Сохранить решение о публикации" });

      form.appendChild(el("fieldset", {}, [
        el("legend", { text: "Публикация на карте платформы" }),
        el("label", { className: P + "-choice" }, [approve, canPublish ? " Одобрить и опубликовать" : " Одобрить (текст не публикуется — нет согласия)"]),
        el("label", { className: P + "-choice" }, [reject, " Отклонить"]),
      ]));
      form.appendChild(el("label", { className: P + "-label", htmlFor: reasonId, text: "Причина (служебно)" }));
      form.appendChild(reason);
      if (canPublish) {
        var redactButton = el("button", { type: "button", className: P + "-link", text: "Скрыть найденные контакты" });
        on(redactButton, "click", function () { publicText.value = redactHints(item.text, item.personal_data_hints || []); });
        form.appendChild(el("label", { className: P + "-label", htmlFor: publicTextId, text: "Публичная версия текста (уберите имена, адреса, контакты)" }));
        form.appendChild(publicText);
        if (item.personal_data_hints && item.personal_data_hints.length) form.appendChild(redactButton);
      }
      form.appendChild(el("label", { className: P + "-label", htmlFor: replyId, text: canPublish ? "Публичный ответ платформы" : "Ответ автору (виден по квитанции)" }));
      form.appendChild(reply);
      if (item.handling_status === "new") form.appendChild(el("small", { className: P + "-muted", text: "Решение переведёт сообщение в статус «В работе» (или «Дан ответ», если ответ заполнен)." }));
      form.appendChild(status);
      form.appendChild(submit);

      on(form, "submit", function (event) {
        event.preventDefault();
        var action = reject.checked ? "reject" : "approve";
        if (reason.value.trim().length < 3) {
          status.textContent = "Укажите причину решения.";
          return;
        }
        var body = { expected_revision: item.revision, action: action, reason: reason.value, public_reply: reply.value.trim() ? reply.value : null };
        if (canPublish && action === "approve" && publicText.value !== (item.public_text || item.text)) body.public_text = publicText.value;
        submitAction(form, submit, status, item, body);
      });
      return form;
    }

    renderTabs(null);
    refresh();
    return {
      refresh: refresh,
      destroy: function () {
        if (searchTimer) clearTimeout(searchTimer);
        life.destroy(removeMarker);
      },
    };
  }

  window.CivicFeedback = {
    version: "civic-v1",
    mount: mount,
    mountModeration: mountModeration,
    createFetchApi: createFetchApi,
  };
})();
