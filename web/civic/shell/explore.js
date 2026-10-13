/* City navigation uses the existing OSM boundaries; it never changes training scores.
 * Street search reads R07's web/civic/map/streets.json (read-only here) and runs locally: no remote geocoder. */
(function (global) {
  "use strict";
  const PREFIX = "civic-explore-";
  const MAX_OPTIONS = 10;
  // Тексты (раунд 14): BirgeShell.t — словари R11, затем запасной shell-text.js; в Node (тесты) — shell-text.js.
  const TEXT = global.BirgeShellText || (typeof require === "function" ? require("./shell-text.js") : null);
  const T = (key, params) => (global.BirgeShell ? global.BirgeShell.t(key, params) : TEXT ? TEXT.text(key, params, "ru") : key);
  // Название района на языке интерфейса: district.<id> у R11, иначе имя из OSM.
  function districtLabel(f) {
    const key = "district." + (f?.properties?.id || "");
    const value = T(key);
    return value && value !== key ? value : f?.properties?.name || "";
  }
  function bounds(geometry) {
    const box = [Infinity, Infinity, -Infinity, -Infinity];
    function visit(coords) {
      if (!Array.isArray(coords)) return;
      if (typeof coords[0] === "number") {
        if (!Number.isFinite(coords[0]) || !Number.isFinite(coords[1])) return;
        box[0] = Math.min(box[0], coords[0]); box[1] = Math.min(box[1], coords[1]);
        box[2] = Math.max(box[2], coords[0]); box[3] = Math.max(box[3], coords[1]);
      } else coords.forEach(visit);
    }
    visit(geometry?.coordinates);
    return box.every(Number.isFinite) ? box : null;
  }

  // ---- pure helpers (unit-tested in tests/civic/R01/explore.test.cjs)
  // Matching ignores case, ё/е, quotes, hyphens and Kazakh letter forms (қ~к, ә~а, ...), and word order.
  const KZ = { "ә": "а", "ғ": "г", "қ": "к", "ң": "н", "ө": "о", "ұ": "у", "ү": "у", "һ": "х", "і": "и", "ё": "е" };
  function normalize(text) {
    return String(text || "").toLocaleLowerCase("ru").replace(/[әғқңөұүһіё]/g, (c) => KZ[c])
      .replace(/[«»"'`’‘“”()]/g, " ").replace(/[-‐–—.,/]/g, " ").replace(/\s+/g, " ").trim();
  }
  function inRing(pt, ring) {
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i], [xj, yj] = ring[j];
      if ((yi > pt[1]) !== (yj > pt[1]) && pt[0] < ((xj - xi) * (pt[1] - yi)) / (yj - yi) + xi) inside = !inside;
    }
    return inside;
  }
  function inPolygon(pt, rings) { return inRing(pt, rings[0]) && !rings.slice(1).some((hole) => inRing(pt, hole)); }
  // Рамка каждого многоугольника района считается один раз: точку вне рамки не проверяем по тысячам вершин
  // (разметка ~5 тыс. улиц по районам занимала ~200 мс главного потока при загрузке — R10 «первый значок ≤ 3 с»).
  const BOXES = new WeakMap();
  function polysOf(f) {
    let polys = BOXES.get(f);
    if (polys) return polys;
    const g = f.geometry;
    polys = (g?.type === "Polygon" ? [g.coordinates] : g?.type === "MultiPolygon" ? g.coordinates : []).map((rings) => {
      let w = Infinity, s = Infinity, e = -Infinity, n = -Infinity;
      for (const [x, y] of rings[0] || []) { if (x < w) w = x; if (x > e) e = x; if (y < s) s = y; if (y > n) n = y; }
      return { rings, box: [w, s, e, n] };
    });
    if (f && typeof f === "object") BOXES.set(f, polys);
    return polys;
  }
  function featureAt(pt, features) {
    for (const f of features || []) {
      if (!f) continue;
      if (polysOf(f).some(({ rings, box }) => pt[0] >= box[0] && pt[0] <= box[2] && pt[1] >= box[1] && pt[1] <= box[3]
        && inPolygon(pt, rings))) return f;
    }
    return null;
  }
  function districtAt(pt, features) { return featureAt(pt, features)?.properties?.name || null; }
  // Each index entry gets a plain-language place hint instead of raw coordinates: the OSM district its
  // centre falls into ("район Есиль"), or "окрестности" outside all six; same-name parts in the same
  // place are numbered west -> east.
  function labelStreets(streets, features) {
    const items = (streets || []).filter((s) => s && typeof s.name === "string" && Array.isArray(s.bbox) && s.bbox.length === 4
      && s.bbox.every(Number.isFinite))
      .map((s, i) => {
        const centre = [(s.bbox[0] + s.bbox[2]) / 2, (s.bbox[1] + s.bbox[3]) / 2];
        const feature = featureAt(centre, features);
        const district = feature?.properties?.name || null;
        return { key: String(i), name: s.name, bbox: s.bbox, centre, district,
          place: feature ? T("district.name", { name: districtLabel(feature) }) : T("shell.explore.place_outside"), norm: normalize(s.name) };
      });
    const groups = new Map(), sameName = new Map();
    for (const it of items) {
      const k = it.norm + "|" + it.place;
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k).push(it);
      sameName.set(it.norm, (sameName.get(it.norm) || 0) + 1);
    }
    for (const list of groups.values()) {
      list.sort((a, b) => a.centre[0] - b.centre[0]);
      if (list.length > 1) list.forEach((it, n) => { it.place = T("shell.explore.place_part", { place: it.place, i: n + 1, n: list.length }); });
    }
    for (const it of items) {
      it.ambiguous = sameName.get(it.norm) > 1;
      it.label = it.name + " — " + it.place;
    }
    return items;
  }
  function matchStreets(items, query) {
    const q = normalize(query);
    if (q.length < 2) return [];
    const words = q.split(" ");
    const scored = [];
    for (const it of items || []) {
      if (!words.every((w) => it.norm.includes(w))) continue;
      const rank = it.norm === q ? 0 : it.norm.startsWith(q) ? 1 : it.norm.split(" ").some((w) => w.startsWith(words[0])) ? 2 : 3;
      scored.push([rank, it]);
    }
    scored.sort((a, b) => a[0] - b[0] || a[1].name.length - b[1].name.length || a[1].name.localeCompare(b[1].name, "ru")
      || a[1].place.localeCompare(b[1].place, "ru"));
    return scored.map((x) => x[1]);
  }

  function mount({ root, map, districts, onNavigate, onObjects, onStreet, onPlace, streetsUrl, placesUrl }) {
    const features = (districts?.features || []).filter((f) => bounds(f.geometry));
    let selected = "", destroyed = false;
    const box = document.createElement("section");
    box.className = "civic-explore";
    // Разметка без текстов: подписи ставит relabel() на языке интерфейса (и заново при ҚАЗ/РУС).
    box.innerHTML = `<div class="civic-explore-row"><label><span data-t="shell.explore.area"></span><select data-t-attr="aria-label:shell.explore.district_label"><option value="" data-t="shell.explore.all_city"></option></select></label><button type="button" class="civic-explore-objects" data-t="shell.explore.to_objects"></button><details><summary data-t="shell.explore.layers" data-t-attr="aria-label:shell.explore.layers_label"></summary><div class="civic-explore-details"><label><input type="checkbox"> <span data-t="shell.explore.district_borders"></span></label><p data-t="shell.explore.coverage"></p><p class="civic-explore-count" role="status"></p><p data-t="shell.explore.borders_source"></p></div></details></div><p class="civic-explore-view" aria-live="polite"></p>`;
    root.append(box);
    const search = document.createElement("form");
    search.className = "civic-explore-search";
    search.setAttribute("role", "search");
    search.innerHTML = `<div class="civic-explore-field"><input type="text" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="${PREFIX}listbox" data-t-attr="aria-label:common.search.label" autocomplete="off" spellcheck="false" enterkeyhint="search"><button type="button" class="civic-explore-clear" data-t-attr="aria-label:common.search.clear" hidden>×</button></div><button type="submit" class="civic-explore-go" data-t="shell.explore.find"></button><ul id="${PREFIX}listbox" class="civic-explore-list" role="listbox" data-t-attr="aria-label:shell.explore.streets_label" hidden></ul><p class="civic-explore-status" role="status" aria-live="polite" hidden></p>`;
    box.append(search);
    // Host notices (e.g. "basemap unavailable") are placed here so they never sit under this box.
    const notices = document.createElement("div");
    notices.className = "civic-explore-notices";
    // Empty registry is stated at city level: "nothing published" is not "nothing happening".
    const registry = document.createElement("p");
    registry.className = "civic-explore-registry";
    registry.setAttribute("role", "status");
    registry.hidden = true;
    box.append(registry, notices);
    // Телефон (≤ 760 px): панель свёрнута в одну кнопку «Территория» 48 px и раскрывается по нажатию — иначе она
    // занимала треть карты над шторкой (UX_REVIEW R11 B1 п. 7). На ноутбуке кнопки нет, панель открыта всегда (CSS).
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "civic-explore-toggle";
    toggle.dataset.t = "shell.explore.area";
    toggle.setAttribute("aria-expanded", "false");
    box.prepend(toggle);
    box.dataset.open = "false";
    const phone = () => typeof global.matchMedia === "function" && global.matchMedia("(max-width: 760px)").matches;
    function setOpen(open) {
      box.dataset.open = open ? "true" : "false";
      toggle.setAttribute("aria-expanded", String(open));
    }
    toggle.addEventListener("click", () => setOpen(box.dataset.open !== "true"));
    const input = search.querySelector("input"), clear = search.querySelector(".civic-explore-clear");
    const list = search.querySelector("ul"), status = search.querySelector(".civic-explore-status");
    const select = box.querySelector("select"), checkbox = box.querySelector("details input");

    let lastSay = null;  // [key, kind, params] — чтобы повторить сообщение на другом языке
    function say(key, kind, params) {
      status.replaceChildren();
      status.hidden = !key;
      status.dataset.kind = key ? kind || "" : "";
      lastSay = key ? [key, kind, params] : null;
      if (!key) return;
      status.append(T(key, params));
      if (kind === "error") {
        const retry = document.createElement("button");
        retry.type = "button"; retry.className = "civic-explore-retry"; retry.textContent = T("common.action.retry");
        retry.addEventListener("click", () => { say("shell.explore.loading", "loading"); loadIndex(); });
        status.append(" ", retry);
      }
    }

    // Clears transient messages but keeps "index unavailable" (and its retry) until the index loads.
    function quiet() { if (index.state !== "error") say(""); }

    // ---- street index: loading / ready / error (with retry)
    let index = { state: "loading", items: [] };
    let controller = null, rawStreets = null, snapshot = "";
    function loadIndex() {
      controller?.abort();
      controller = new AbortController();
      index = { state: "loading", items: [] };
      fetch(streetsUrl || "/civic/map/streets.json", { signal: controller.signal }).then((r) => {
        if (!r.ok) throw new Error("street index HTTP " + r.status);
        return r.json();
      }).then((data) => {
        if (destroyed) return;
        if (!Array.isArray(data?.streets)) throw new Error("street index format");
        snapshot = String(data.source?.snapshot_at || "").slice(0, 10);
        rawStreets = data.streets;
        index = { state: "ready", items: labelStreets(rawStreets, features) };
        input.title = snapshot ? T("shell.explore.street_hint_date", { date: snapshot }) : T("shell.explore.street_hint");
        if (status.dataset.kind === "loading") say("");
        if (input.value.trim().length > 1 && document.activeElement === input) refresh();
      }).catch((e) => {
        if (destroyed || e.name === "AbortError") return;
        index = { state: "error", items: [] };
        close();
        say("shell.explore.index_error", "error");
      });
    }

    // ---- чистый дизайн (R11 CLEAN_PASS №2): одно поле поиска — «Вся Астана», районы, места с жалобами (цели R07 /heat:
    // остановки, участки улиц, дворы) и улицы (индекс R07). Места грузятся при первом фокусе, один раз.
    let places = { state: "idle", items: [] };
    const lang = () => (global.BirgeI18n?.getLang?.() === "kk" ? "kk" : "ru");
    function placeName(target) { return (lang() === "kk" ? target?.label_kk : target?.label_ru) || target?.label_ru || target?.label_kk || ""; }
    function loadPlaces() {
      if (places.state !== "idle" || typeof fetch !== "function") return;
      places = { state: "loading", items: [] };
      fetch(placesUrl || "/api/civic/v2/heat?days=30", { headers: { Accept: "application/json" } }).then((r) => (r.ok ? r.json() : null)).then((body) => {
        if (destroyed) return;
        const items = (body?.data?.items || body?.items || []).filter((it) => it?.target?.kind && it.target.kind !== "district" && it.target.id);
        places = { state: "ready", items };
        if (document.activeElement === input && normalize(input.value)) refresh();
      }).catch(() => { places = { state: "error", items: [] }; });
    }
    function cityAndDistricts(q) {
      const n = normalize(q);
      const city = { kind: "city", name: T("common.search.all_city"), place: "" };
      const ds = features.map((f) => ({ kind: "district", id: f.properties.id, name: districtLabel(f), place: T("heat.kind.district") }));
      if (!n) return [city, ...ds];
      // Одна буква — только с начала слова («а» → «Алматы», не «Вся Астана» по букве внутри слова).
      const hit = n.length < 2 ? (name) => normalize(name).split(" ").some((w) => w.startsWith(n)) : (name) => normalize(name).includes(n);
      return [city, ...ds].filter((o) => hit(o.name));
    }
    // Эталон A, правило Linear 1: подсказки с первой буквы. Горячие места — у R07 (heat.suggest: с начала слова, по
    // числу жалоб); без R07 — свой список /heat, как раньше.
    function matchPlaces(q) {
      const n = normalize(q);
      if (!n) return [];
      const heat = global.CivicShell?.heat;
      if (typeof heat?.suggest === "function") {
        try {
          return (heat.suggest(q, 5) || []).filter((it) => it && it.kind && it.id && it.label).map((it) => ({ kind: "place",
            target: { kind: it.kind, id: it.id, label_ru: it.label, label_kk: it.label }, name: it.label, level: it.level,
            place: [it.topic, T("common.people", { n: it.count || 0 })].filter(Boolean).join(" · ") }));
        } catch (e) { /* R07 не готов — свой список ниже */ }
      }
      if (places.state !== "ready") return [];
      return places.items.map((it) => ({ kind: "place", target: it.target, name: placeName(it.target),
        place: T("common.people", { n: it.count || 0 }) }))
        .filter((o) => o.name && normalize(o.name).includes(n)).slice(0, 5);
    }
    // Остановки, дворы, парки и площадки (и улицы на первой букве) — индекс R12 web/civic/map/search_index.json
    // (OpenStreetMap, снимок 06.05.2026). С двух букв улицы — по-прежнему из streets.json (точнее подпись района).
    let sidx = { state: "idle", index: null };
    function loadSearchIndex() {
      const S12 = global.BirgeSearchIndex;
      if (sidx.state !== "idle" || !S12 || typeof S12.load !== "function") return;
      sidx = { state: "loading", index: null };
      S12.load("/civic/map/search_index.json").then((ix) => {
        if (destroyed) return;
        sidx = { state: "ready", index: ix };
        if (document.activeElement === input && normalize(input.value)) refresh();
      }).catch(() => { sidx = { state: "idle", index: null }; });  // ошибка — следующая попытка при фокусе
    }
    const KIND_KEY = { bus_stop: "stop", yard: "yard", park: "park", pitch: "pitch", playground: "playground" };
    function matchIndex(q, hot) {
      const n = normalize(q);
      if (!n || sidx.state !== "ready") return [];
      const exclude = hot.map((h) => h.target.id);
      let found = [];
      // с двух букв улицы отсеиваются ниже — запас, чтобы остановки и дворы не вытеснялись улицами из первых строк R12
      try { found = sidx.index.query(q, { lang: lang(), limit: n.length < 2 ? 12 : 60, exclude }) || []; } catch (e) { return []; }
      const districtName = (id) => { const f = features.find((x) => x.properties?.id === id); return f ? T("district.name", { name: districtLabel(f) }) : ""; };
      const out = [], seen = new Set();
      for (const r of found) {
        if (!r || !Array.isArray(r.point)) continue;
        // Остановка по обе стороны улицы — две точки OSM с одним названием: в подсказках одна строка.
        const same = r.kind + "|" + normalize(r.label) + "|" + (r.district || "");
        if (seen.has(same)) continue;
        seen.add(same);
        if (r.kind === "street") {
          if (n.length >= 2 || !Array.isArray(r.bbox) || r.bbox.length !== 4) continue;   // с двух букв — streets.json
          out.push({ kind: "street", name: r.label, bbox: r.bbox, centre: r.point, district: r.district || null,
            place: districtName(r.district) || T("shell.explore.place_outside") });
          continue;
        }
        const kindText = KIND_KEY[r.kind] ? T("shell.explore.kind." + KIND_KEY[r.kind]) : "";
        out.push({ kind: "spot", spot: r.kind, id: r.id, name: r.label, centre: r.point, district: r.district || null,
          place: [kindText, districtName(r.district)].filter(Boolean).join(" · ") });
      }
      return out.slice(0, 6);
    }

    // ---- the chosen street is marked by a label at the centre of its OSM extent (the index has no
    // street geometry, so this is an approximate place, said so in the label's title).
    let pin = null;
    function unpin() { pin?.remove(); pin = null; }
    function pinStreet(it) {
      unpin();
      const Marker = global.maplibregl?.Marker;
      if (!map || !Marker) return;
      const el = document.createElement("div");
      el.className = "civic-explore-pin";
      el.title = T("shell.explore.pin_title");
      const label = document.createElement("span");
      label.textContent = it.name;
      el.append(label);
      pin = new Marker({ element: el, anchor: "bottom" }).setLngLat(it.centre).addTo(map);
    }

    // ---- combobox (ARIA 1.2 pattern: focus stays in the input, options via aria-activedescendant)
    let options = [], active = -1;
    function close() {
      list.hidden = true; list.replaceChildren(); options = []; active = -1;
      input.setAttribute("aria-expanded", "false"); input.removeAttribute("aria-activedescendant");
    }
    function highlight(n) {
      active = options.length ? (n + options.length) % options.length : -1;
      list.querySelectorAll("[role=option]").forEach((li, i) => li.setAttribute("aria-selected", String(i === active)));
      if (active < 0) { input.removeAttribute("aria-activedescendant"); return; }
      const li = document.getElementById(PREFIX + "opt-" + active);
      input.setAttribute("aria-activedescendant", li.id);
      li.scrollIntoView({ block: "nearest" });
    }
    function render(matches) {
      list.replaceChildren();
      options = matches.slice(0, MAX_OPTIONS);
      options.forEach((it, i) => {
        const li = document.createElement("li");
        li.id = PREFIX + "opt-" + i; li.setAttribute("role", "option"); li.setAttribute("aria-selected", "false");
        if (it.kind) li.dataset.kind = it.kind;
        if (it.level) li.dataset.level = String(it.level);
        if (it.spot) li.dataset.spot = it.spot;
        const name = document.createElement("span"); name.className = "civic-explore-opt-name"; name.textContent = it.name;
        const place = document.createElement("span"); place.className = "civic-explore-opt-place"; place.textContent = it.place;
        li.append(name, place);
        li.addEventListener("pointerdown", (e) => e.preventDefault());  // keep focus in the input
        li.addEventListener("click", () => choose(it));
        list.append(li);
      });
      if (matches.length > options.length) {
        const more = document.createElement("li");
        more.className = "civic-explore-more"; more.setAttribute("role", "presentation");
        more.textContent = T("shell.explore.more", { n: matches.length - options.length });
        list.append(more);
      }
      list.hidden = !options.length;
      input.setAttribute("aria-expanded", String(!!options.length));
      active = -1; input.removeAttribute("aria-activedescendant");
    }
    function refresh(onFocus) {
      clear.hidden = !input.value;
      const q = input.value.trim();
      // Пустое поле в фокусе — «Вся Астана» и районы списком. Эталон A (правило Linear 1): подсказки с первой буквы —
      // районы, горячие места (R07), остановки, дворы и парки (R12), улицы.
      if (!normalize(q).length) { if (onFocus === true) render(cityAndDistricts("")); else close(); quiet(); return; }
      const hot = matchPlaces(q);
      const top = [...cityAndDistricts(q), ...hot, ...matchIndex(q, hot)];
      const streets = index.state === "ready" ? matchStreets(index.items, q) : [];
      const matches = [...top, ...streets];
      render(matches);
      if (matches.length) { say(""); return; }
      if (index.state === "loading") { say("shell.explore.loading", "loading"); return; }
      if (index.state === "error") return;
      say("shell.explore.not_found", "none");
    }
    function choose(it) {
      if (it.kind === "city" || it.kind === "district") {  // район или вся Астана — как выбор в списке районов
        input.value = it.kind === "city" ? "" : it.name; clear.hidden = !input.value;
        close();
        select.value = it.kind === "city" ? "" : it.id;
        select.dispatchEvent(new Event("change"));
        if (it.kind === "district") { input.value = it.name; clear.hidden = false; }
        return;
      }
      if (it.kind === "place") {  // место с жалобами — карточка цели R07
        input.value = it.name; clear.hidden = false;
        close(); unpin(); quiet();
        onPlace?.(it.target);
        if (phone()) setOpen(false);
        return;
      }
      if (it.kind === "spot") {  // остановка, двор, парк из индекса R12 — без жалоб: карта к месту и метка (данные OSM)
        input.value = it.name; clear.hidden = false;
        close();
        selected = ""; select.value = ""; paint();
        say("shell.explore.chosen_spot", "chosen", { name: it.name, place: it.place });
        pinStreet(it);
        const d = 0.0012;
        onStreet?.({ name: it.name, label: it.name, place: it.place, district: it.district, spot: it.spot,
          bbox: [it.centre[0] - d, it.centre[1] - d * 0.63, it.centre[0] + d, it.centre[1] + d * 0.63] });
        if (phone()) setOpen(false);
        return;
      }
      input.value = it.name; clear.hidden = false;
      close();
      selected = ""; select.value = ""; paint();
      say("shell.explore.chosen", "chosen", { name: it.name, place: it.place });
      pinStreet(it);
      onStreet?.({ name: it.name, label: it.label, place: it.place, district: it.district, bbox: it.bbox });
      if (phone()) setOpen(false);  // улица выбрана — карта снова свободна
    }
    input.addEventListener("input", refresh);
    // Фокус пустого поля самим человеком — «Вся Астана» и районы списком; после «×» (фокус из кода) — без списка.
    let quietFocus = false;
    input.addEventListener("focus", () => { loadPlaces(); loadSearchIndex(); if (status.dataset.kind !== "chosen") refresh(!quietFocus); quietFocus = false; });
    // Нажатие на уже активное пустое поле тоже показывает «Вся Астана» и районы (после выбора или Esc).
    input.addEventListener("click", () => { if (!input.value.trim() && list.hidden) { loadPlaces(); refresh(true); } });
    input.addEventListener("blur", () => setTimeout(() => { if (document.activeElement !== input) close(); }, 0));
    input.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        if (list.hidden) refresh();
        if (options.length) highlight(active < 0 ? (e.key === "ArrowDown" ? 0 : options.length - 1) : active + (e.key === "ArrowDown" ? 1 : -1));
      } else if (e.key === "Escape") {
        // Handled here: the shell's Escape (close drawers/cards) must not also run.
        if (!list.hidden) { e.preventDefault(); close(); }
        else if (input.value) { e.preventDefault(); input.value = ""; unpin(); refresh(); }
      } else if (e.key === "Tab") close();
    });
    search.addEventListener("submit", (event) => {
      event.preventDefault();
      if (active >= 0 && options[active]) { choose(options[active]); return; }
      const q = input.value.trim();
      if (!q) { input.focus(); return; }
      const hot = matchPlaces(q);
      const top = [...cityAndDistricts(q), ...hot, ...matchIndex(q, hot)];
      const exactTop = top.filter((m) => normalize(m.name) === normalize(q));
      if (exactTop.length === 1) { choose(exactTop[0]); return; }
      if (index.state === "loading" && !top.length) { say("shell.explore.loading", "loading"); return; }
      const streets = index.state === "ready" ? matchStreets(index.items, q) : [];
      const exact = streets.filter((m) => m.norm === normalize(q));
      const matches = [...top, ...streets];
      if (matches.length === 1 || (!top.length && exact.length === 1)) { choose(exact.length === 1 && !top.length ? exact[0] : matches[0]); return; }
      render(matches);
      if (matches.length) { highlight(0); say("shell.explore.found_pick", "count", { n: matches.length }); input.focus(); }
      else say("shell.explore.not_found", "none");
    });
    clear.addEventListener("click", () => { input.value = ""; unpin(); refresh(); quietFocus = document.activeElement !== input; input.focus(); quietFocus = false; });

    // ---- districts
    features.forEach((f) => {
      const option = document.createElement("option");
      option.value = f.properties.id; option.dataset.district = "1";
      select.append(option);
    });
    // Все подписи блока на языке интерфейса; вызывается при запуске и при переключении ҚАЗ/РУС.
    let records = null;
    function relabel() {
      if (destroyed) return;
      box.setAttribute("aria-label", T("shell.explore.label"));
      for (const node of box.querySelectorAll("[data-t]")) node.textContent = T(node.dataset.t);
      for (const node of box.querySelectorAll("[data-t-attr]")) {
        for (const pair of node.dataset.tAttr.split(";")) {
          const [attr, key] = pair.split(":");
          node.setAttribute(attr, T(key));
        }
      }
      select.querySelectorAll("option[data-district]").forEach((option, i) => { option.textContent = districtLabel(features[i]); });
      // Узкое поле в шапке (проектор 1024, казахский): короткая подсказка «Іздеу / Поиск», а не обрезанная длинная.
      const narrow = phone() || parseFloat(box.style.getPropertyValue("--be-width")) < 300;
      input.placeholder = T(narrow ? "common.search.short" : "common.search.placeholder_clean");
      map?.getSource?.(PREFIX + "labels")?.setData(labelPoints());  // подписи районов — на новом языке
      if (index.state === "ready") {
        index = { state: "ready", items: labelStreets(rawStreets, features) };
        input.title = snapshot ? T("shell.explore.street_hint_date", { date: snapshot }) : T("shell.explore.street_hint");
      }
      if (lastSay) say(...lastSay);
      if (records) showRecords(records);
    }
    // Подписи районов на уровне города (владелец, читаемость карты п. 7): точка — центр района из данных или его рамки.
    function labelPoints() {
      return { type: "FeatureCollection", features: features.map((f) => {
        const p = f.properties || {}, b = bounds(f.geometry);
        const at = Number.isFinite(p.center_lon) && Number.isFinite(p.center_lat) ? [p.center_lon, p.center_lat] : [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2];
        return { type: "Feature", properties: { id: p.id, name: districtLabel(f) }, geometry: { type: "Point", coordinates: at } };
      }) };
    }
    // Границы районов: тонкие и нейтральные (зелёный на карте — только «исправлено»), видны на уровне города и гаснут
    // к 13-му масштабу; «Слои → Границы районов» оставляет их на любом масштабе.
    const cityOpacity = ["interpolate", ["linear"], ["zoom"], 9, 0.7, 12, 0.5, 13, 0];
    function paint() {
      if (destroyed || !map || !map.getStyle()?.layers) return;
      if (!map.getSource(PREFIX + "districts")) map.addSource(PREFIX + "districts", { type: "geojson", data: { type: "FeatureCollection", features } });
      if (!map.getLayer(PREFIX + "lines")) {
        const before = map.getStyle().layers.find((l) => l.type === "symbol")?.id;
        map.addLayer({ id: PREFIX + "lines", type: "line", source: PREFIX + "districts", paint: {
          "line-color": "#8e8a80", "line-width": ["interpolate", ["linear"], ["zoom"], 9, 0.8, 14, 1.2], "line-opacity": cityOpacity,
        } }, before);
        map.addLayer({ id: PREFIX + "selected", type: "line", source: PREFIX + "districts", paint: {
          "line-color": "#4f5a55", "line-width": 2.5,
        }, filter: ["==", ["get", "id"], selected] }, before);
      }
      const style = map.getStyle();
      if (style.glyphs && !map.getLayer(PREFIX + "names")) {  // без шрифтов (запасной фон) подписи не рисуем
        const font = style.layers.find((l) => l.type === "symbol" && l.layout?.["text-font"])?.layout["text-font"];
        if (!map.getSource(PREFIX + "labels")) map.addSource(PREFIX + "labels", { type: "geojson", data: labelPoints() });
        map.addLayer({ id: PREFIX + "names", type: "symbol", source: PREFIX + "labels", maxzoom: 12.5,
          layout: { "text-field": ["get", "name"], "text-font": Array.isArray(font) ? font : ["Noto Sans Regular"], "text-size": 13,
            "text-offset": [0, 1.9], "text-anchor": "top", "text-allow-overlap": false },
          paint: { "text-color": "#5f5b53", "text-halo-color": "#ffffff", "text-halo-width": 1.5,
            "text-opacity": ["interpolate", ["linear"], ["zoom"], 11.5, 1, 12.5, 0] } });
      }
      map.setLayoutProperty(PREFIX + "lines", "visibility", "visible");
      map.setPaintProperty(PREFIX + "lines", "line-opacity", checkbox.checked ? 0.7 : cityOpacity);
      map.setFilter(PREFIX + "selected", ["==", ["get", "id"], selected]);
    }
    select.addEventListener("change", () => {
      selected = select.value;
      input.value = ""; clear.hidden = true; close(); quiet(); unpin();
      paint();
      onNavigate(features.find((f) => f.properties.id === selected) || null);
      if (phone()) setOpen(false);
    });
    checkbox.addEventListener("change", paint);
    box.querySelector(".civic-explore-objects").addEventListener("click", onObjects);
    map?.on("style.load", paint);
    paint();
    relabel();
    const offLang = global.BirgeI18n?.onChange?.(relabel);
    // Индекс улиц — не на пути к первому значку карты (R10 правило 5): в простое браузера (не позже 4 с) или сразу,
    // как человек тронет поле поиска.
    let indexAsked = false;
    const askIndex = () => { if (indexAsked || destroyed) return; indexAsked = true; loadIndex(); };
    input.addEventListener("pointerdown", askIndex);
    input.addEventListener("focus", askIndex);
    if (typeof global.requestIdleCallback === "function") global.requestIdleCallback(askIndex, { timeout: 4000 });
    else setTimeout(askIndex, 2500);
    const view = box.querySelector(".civic-explore-view");
    function showRecords(items) {
      records = items;
      const demo = items.filter((x) => x.evidence === "synthetic").length;
      box.querySelector(".civic-explore-count").textContent = T("shell.explore.count", { n: items.length, demo });
      registry.hidden = items.length > 0;
      registry.textContent = items.length ? "" : T("shell.explore.registry_empty");
    }
    return {
      noticeSlot: notices,
      // What the camera shows now (city overview / district / street / all records), so the three
      // look different even when the map itself is plain (offline basemap).
      setView(text, kind) { view.textContent = text || ""; view.dataset.kind = kind || ""; },
      reset() { selected = ""; select.value = ""; input.value = ""; clear.hidden = true; close(); quiet(); unpin(); paint(); },
      setOpen,
      updateRecords(items) { showRecords(items); },
      destroy() {
        destroyed = true; controller?.abort(); unpin(); map?.off("style.load", paint);
        if (typeof offLang === "function") offLang();
        for (const id of [PREFIX + "selected", PREFIX + "lines"]) if (map?.getLayer(id)) map.removeLayer(id);
        if (map?.getSource(PREFIX + "districts")) map.removeSource(PREFIX + "districts");
        box.remove();
      },
    };
  }
  global.CivicExplore = { mount, bounds, normalize, labelStreets, matchStreets, districtAt };
  if (typeof module !== "undefined") module.exports = { bounds, normalize, labelStreets, matchStreets, districtAt };
})(typeof window !== "undefined" ? window : globalThis);
