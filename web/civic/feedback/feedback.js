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
  var CATEGORIES = [
    ["roads", "Дороги"],
    ["sidewalks", "Тротуары и пешеходные пути"],
    ["transport_stops", "Остановки транспорта"],
    ["lighting", "Освещение"],
    ["landscaping", "Благоустройство и озеленение"],
    ["other", "Другое"],
  ];
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
  var MODERATION_TABS = [
    ["pending", "Ожидают"],
    ["approved", "Проверены"],
    ["rejected", "Отклонены"],
    ["all", "Все"],
  ];
  // Черновики живут только в памяти страницы: переживают закрытие карточки, не перезагрузку.
  var drafts = new Map();
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
    var draft = drafts.get(key) || {
      kind: "problem", category: "", text: "", consent: null, requestId: requestId(), confirm: false,
    };
    drafts.set(key, draft);
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
      on(input, "change", function () { draft.kind = input.value; });
      kindSet.appendChild(el("label", { className: P + "-choice" }, [input, " " + pair[1]]));
    });

    var category = el("select", { id: ids.category, required: true });
    category.appendChild(el("option", { value: "", text: "Выберите категорию" }));
    CATEGORIES.forEach(function (pair) {
      category.appendChild(el("option", { value: pair[0], text: pair[1], selected: draft.category === pair[0] }));
    });
    on(category, "change", function () { draft.category = category.value; clearFieldError("category"); });

    var textarea = el("textarea", {
      id: ids.text, rows: 5, maxLength: TEXT_MAX, required: true,
      placeholder: "Что происходит и где именно? Например: нет прохода вдоль ограждения у остановки.",
      "aria-describedby": ids.counter,
    });
    textarea.value = draft.text;
    var counter = el("small", { id: ids.counter, className: P + "-muted" });
    function updateCounter() { counter.textContent = textarea.value.length + " / " + TEXT_MAX + ". " + PRIVACY_HINT; }
    updateCounter();
    on(textarea, "input", function () { draft.text = textarea.value; updateCounter(); clearFieldError("text"); });

    var consentSet = el("fieldset", { className: P + "-consent" }, [
      el("legend", { text: "Публикация текста" }),
    ]);
    var consentName = nextId("consent");
    [
      [true, "Можно опубликовать текст на карте после проверки модератором платформы"],
      [false, "Не публиковать: текст увидят только модераторы платформы"],
    ].forEach(function (pair) {
      var input = el("input", { type: "radio", name: consentName, value: String(pair[0]), checked: draft.consent === pair[0] });
      on(input, "change", function () { draft.consent = pair[0]; clearFieldError("consent_public"); });
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
          drafts.delete(key);
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
          if (info.code === "request_id_conflict") draft.requestId = requestId();
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
            receiptStatus.textContent = "Статус: " + data.moderation_label + (data.is_public ? " · текст опубликован" : "");
            clear(actionStatus);
            if (data.public_reply) {
              actionStatus.appendChild(el("span", { text: "Ответ модератора платформы: " }));
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
    var filters = { moderation: "pending", category: "", consent: "" };
    var selectedId = null;
    var loadToken = 0;
    var cached = {};

    clear(root);
    root.classList.add(P);
    var container = el("section", { className: P + "-moderation", "aria-label": "Модерация сообщений жителей" });
    var header = el("div", { className: P + "-mod-header" }, [
      el("h3", { className: P + "-title", text: "Сообщения жителей — модерация" }),
      el("p", { className: P + "-muted", text: "Решения влияют только на публикацию на платформе. Они не регистрируют официальное обращение и не означают начала работ." }),
    ]);
    var tabs = el("div", { className: P + "-tabs", role: "tablist" });
    var categoryFilter = el("select", { "aria-label": "Категория" });
    categoryFilter.appendChild(el("option", { value: "", text: "Все категории" }));
    CATEGORIES.forEach(function (pair) { categoryFilter.appendChild(el("option", { value: pair[0], text: pair[1] })); });
    var consentFilter = el("select", { "aria-label": "Согласие на публикацию" });
    [["", "Любое согласие"], ["true", "Разрешена публикация"], ["false", "Без публикации"]].forEach(function (pair) {
      consentFilter.appendChild(el("option", { value: pair[0], text: pair[1] }));
    });
    var listStatus = el("div", { className: P + "-status", role: "status", "aria-live": "polite" });
    var list = el("ul", { className: P + "-queue" });
    var detail = el("div", { className: P + "-detail", "aria-live": "polite" });
    container.appendChild(header);
    container.appendChild(tabs);
    container.appendChild(el("div", { className: P + "-filters" }, [categoryFilter, consentFilter]));
    container.appendChild(listStatus);
    container.appendChild(el("div", { className: P + "-mod-body" }, [list, detail]));
    root.appendChild(container);

    on(categoryFilter, "change", function () { filters.category = categoryFilter.value; refresh(); });
    on(consentFilter, "change", function () { filters.consent = consentFilter.value; refresh(); });

    function renderTabs(counts) {
      clear(tabs);
      MODERATION_TABS.forEach(function (pair) {
        var count = pair[0] === "all" || !counts ? "" : " (" + (counts[pair[0]] || 0) + ")";
        var button = el("button", {
          type: "button", role: "tab", className: P + "-tab",
          "aria-selected": String(filters.moderation === pair[0]), text: pair[1] + count,
        });
        on(button, "click", function () { filters.moderation = pair[0]; refresh(); });
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
      var query = ["moderation=" + encodeURIComponent(filters.moderation)];
      if (filters.category) query.push("category=" + encodeURIComponent(filters.category));
      if (filters.consent) query.push("consent=" + encodeURIComponent(filters.consent));
      listStatus.textContent = "Загрузка…";
      return api.request("GET", "/staff/feedback?" + query.join("&")).then(
        function (data) {
          if (life.destroyed || token !== loadToken) return;
          listStatus.textContent = "";
          renderTabs(data.counts);
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
            el("span", { className: P + "-chip", text: KIND_SHORT[item.kind] || item.kind }),
            el("span", { className: P + "-chip " + P + "-chip-muted", text: item.category_label }),
            el("span", { className: P + "-muted", text: "#" + item.id + " · " + formatDate(item.created_at) }),
          ]),
          el("span", { className: P + "-excerpt", text: item.text }),
          el("span", { className: P + "-muted", text: (item.object_id ? "Объект " + item.object_id : "Место на карте") + (flags.length ? " · " + flags.join(" · ") : "") }),
        ]);
        on(button, "click", function () { select(item.id); });
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
      api.request("GET", "/staff/feedback/" + encodeURIComponent(id)).then(
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

    function renderDetail(data) {
      var item = data.item;
      var object = data.object;
      clear(detail);
      removeMarker();
      var consentText = item.consent_withdrawn_at
        ? "Согласие на публикацию отозвано автором " + formatDate(item.consent_withdrawn_at)
        : item.consent_public ? "Автор разрешил публикацию текста после проверки" : "Автор НЕ разрешил публиковать текст";
      detail.appendChild(el("h4", { text: "Сообщение #" + item.id + " · " + item.moderation_label }));
      detail.appendChild(el("p", { className: P + "-muted", text: "Ревизия " + item.revision + " · получено " + formatDate(item.created_at) }));
      if (data.degraded) {
        detail.appendChild(el("p", { className: P + "-warning-text", text: "Карточка собрана из очереди: журнал, похожие сообщения и сведения об объекте недоступны в этой сборке (нет маршрута GET /staff/feedback/{id})." }));
      }
      detail.appendChild(el("p", { className: item.consent_public && !item.consent_withdrawn_at ? P + "-ok" : P + "-warning-text", text: consentText }));
      detail.appendChild(el("div", { className: P + "-private" }, [
        el("small", { text: "Исходный текст — только для модераторов" }),
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
      var clf = item.classifier || {};
      if (clf.suggestion) {
        detail.appendChild(el("p", { className: P + "-muted", text: "Подсказка модели (" + (clf.suggestion.model_version || "версия неизвестна") + "): " + clf.suggestion.label_text + (clf.suggestion.score !== null && clf.suggestion.score !== undefined ? ", оценка " + clf.suggestion.score + " (" + (clf.suggestion.score_kind || "не вероятность") + ")" : "") + ". Категорию жителя не меняет." }));
      } else {
        detail.appendChild(el("p", { className: P + "-muted", text: "Подсказка модели: " + ({ unavailable: "модель не подключена", error: "ошибка модели", timeout: "модель не ответила", invalid: "некорректный ответ модели" }[clf.status] || "нет") + "." }));
      }
      if (data.similar && data.similar.length) {
        var similarList = el("ul", { className: P + "-similar" });
        data.similar.forEach(function (s) {
          var open = el("button", { type: "button", className: P + "-link", text: "#" + s.id + " (" + Math.round(s.score * 100) + "% совпадение слов, " + s.moderation + ")" });
          on(open, "click", function () { select(s.id); });
          similarList.appendChild(el("li", {}, [open, el("span", { className: P + "-muted", text: " " + s.excerpt })]));
        });
        detail.appendChild(el("details", { open: true }, [el("summary", { text: "Похожие сообщения — подсказка, не объединение" }), similarList]));
      }

      detail.appendChild(renderDecisionForm(item));

      if (!data.history) return;
      var history = el("ol", { className: P + "-history" });
      data.history.forEach(function (h) {
        history.appendChild(el("li", {}, [
          el("span", { text: formatDate(h.at) + " · " + (HISTORY_LABELS[h.action] || h.action) + " · ревизия " + h.revision + (h.actor ? " · " + h.actor : "") }),
          h.reason ? el("span", { className: P + "-muted", text: " — " + h.reason }) : null,
          h.is_public ? el("span", { className: P + "-chip", text: "публично" }) : null,
        ]));
      });
      detail.appendChild(el("details", {}, [el("summary", { text: "Журнал действий" }), history]));
    }

    function renderDecisionForm(item) {
      var form = el("form", { className: P + "-decision", noValidate: true });
      var actionName = nextId("action");
      var approve = el("input", { type: "radio", name: actionName, value: "approve", checked: item.moderation !== "rejected" });
      var reject = el("input", { type: "radio", name: actionName, value: "reject", checked: item.moderation === "rejected" });
      var reasonId = nextId("reason");
      var reason = el("textarea", { id: reasonId, rows: 2, maxLength: 500, required: true, placeholder: "Причина решения — видна только редакторам" });
      var canPublish = item.consent_public && !item.consent_withdrawn_at;
      var publicTextId = nextId("public-text");
      var publicText = el("textarea", { id: publicTextId, rows: 4, maxLength: 2000 });
      publicText.value = item.public_text || item.text;
      var replyId = nextId("reply");
      var reply = el("textarea", { id: replyId, rows: 3, maxLength: 2000, placeholder: "Необязательно. Не обещайте сроки и работы, которые не подтверждены." });
      reply.value = item.public_reply || "";
      var status = el("div", { className: P + "-status", role: "status", "aria-live": "polite" });
      var submit = el("button", { type: "submit", className: P + "-primary", text: "Сохранить решение" });

      form.appendChild(el("fieldset", {}, [
        el("legend", { text: "Решение модератора платформы" }),
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
      form.appendChild(el("label", { className: P + "-label", htmlFor: replyId, text: canPublish ? "Публичный ответ" : "Ответ автору (виден по квитанции)" }));
      form.appendChild(reply);
      form.appendChild(status);
      form.appendChild(submit);

      var busy = false;
      on(form, "submit", function (event) {
        event.preventDefault();
        if (busy) return;
        var action = reject.checked ? "reject" : "approve";
        if (reason.value.trim().length < 3) {
          status.textContent = "Укажите причину решения.";
          return;
        }
        var body = { expected_revision: item.revision, action: action, reason: reason.value, public_reply: reply.value.trim() ? reply.value : null };
        if (canPublish && action === "approve" && publicText.value !== (item.public_text || item.text)) body.public_text = publicText.value;
        busy = true;
        submit.disabled = true;
        status.textContent = "Сохраняем…";
        api.request("POST", "/staff/feedback/" + encodeURIComponent(item.id) + "/moderate", body).then(
          function () {
            busy = false;
            if (life.destroyed) return;
            refresh();
            select(item.id);
          },
          function (err) {
            busy = false;
            submit.disabled = false;
            if (life.destroyed) return;
            var info = errorInfo(err);
            if (info.status === 409) {
              status.textContent = "Сообщение уже изменено другим действием. Карточка обновлена — проверьте и повторите.";
              select(item.id);
              return;
            }
            var extra = info.fields ? " " + Object.keys(info.fields).map(function (k) { return info.fields[k]; }).join(" ") : "";
            status.textContent = staffError(err, "Не удалось сохранить решение.") + extra;
          }
        );
      });
      return form;
    }

    renderTabs(null);
    refresh();
    return {
      refresh: refresh,
      destroy: function () { life.destroy(removeMarker); },
    };
  }

  window.CivicFeedback = {
    version: "civic-v1",
    mount: mount,
    mountModeration: mountModeration,
    createFetchApi: createFetchApi,
  };
})();
