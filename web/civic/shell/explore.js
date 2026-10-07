/* City navigation uses the existing OSM boundaries; it never changes training scores.
 * Street search reads R07's web/civic/map/streets.json (read-only here) and runs locally: no remote geocoder. */
(function (global) {
  "use strict";
  const PREFIX = "civic-explore-";
  const MAX_OPTIONS = 10;
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
  function districtAt(pt, features) {
    for (const f of features || []) {
      const g = f.geometry;
      const polys = g?.type === "Polygon" ? [g.coordinates] : g?.type === "MultiPolygon" ? g.coordinates : [];
      if (polys.some((rings) => inPolygon(pt, rings))) return f.properties?.name || null;
    }
    return null;
  }
  // Each index entry gets a plain-language place hint instead of raw coordinates: the OSM district its
  // centre falls into ("район Есиль"), or "окрестности" outside all six; same-name parts in the same
  // place are numbered west -> east.
  function labelStreets(streets, features) {
    const items = (streets || []).filter((s) => s && typeof s.name === "string" && Array.isArray(s.bbox) && s.bbox.length === 4
      && s.bbox.every(Number.isFinite))
      .map((s, i) => {
        const centre = [(s.bbox[0] + s.bbox[2]) / 2, (s.bbox[1] + s.bbox[3]) / 2];
        const district = districtAt(centre, features);
        return { key: String(i), name: s.name, bbox: s.bbox, centre, district,
          place: district ? "район " + district : "окрестности, вне границ районов", norm: normalize(s.name) };
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
      if (list.length > 1) list.forEach((it, n) => { it.place += ` · участок ${n + 1} из ${list.length}`; });
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

  function mount({ root, map, districts, onNavigate, onObjects, onStreet, streetsUrl }) {
    const features = (districts?.features || []).filter((f) => bounds(f.geometry));
    let selected = "", destroyed = false;
    const box = document.createElement("section");
    box.className = "civic-explore";
    box.setAttribute("aria-label", "Навигация по Астане");
    box.innerHTML = `<div class="civic-explore-row"><label><span>Территория</span><select aria-label="Район Астаны"><option value="">Вся Астана</option></select></label><button type="button" class="civic-explore-objects">К объектам</button><details><summary aria-label="Покрытие и слои карты">Слои</summary><div class="civic-explore-details"><label><input type="checkbox"> Границы районов</label><p>Карта доступна по всей Астане. Пустое место означает отсутствие опубликованных записей, а не отсутствие работ.</p><p class="civic-explore-count" role="status"></p><p>Границы: OpenStreetMap, снимок 23.09.2026. Это общественная карта, не кадастровые границы.</p></div></details></div>`;
    root.append(box);
    const search = document.createElement("form");
    search.className = "civic-explore-search";
    search.setAttribute("role", "search");
    search.innerHTML = `<div class="civic-explore-field"><input type="text" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="${PREFIX}listbox" placeholder="Улица Астаны" aria-label="Найти улицу в Астане" autocomplete="off" spellcheck="false" enterkeyhint="search"><button type="button" class="civic-explore-clear" aria-label="Очистить поиск" hidden>×</button></div><button type="submit" class="civic-explore-go">Найти</button><ul id="${PREFIX}listbox" class="civic-explore-list" role="listbox" aria-label="Улицы Астаны" hidden></ul><p class="civic-explore-status" role="status" aria-live="polite" hidden></p>`;
    box.append(search);
    // Host notices (e.g. "basemap unavailable") are placed here so they never sit under this box.
    const notices = document.createElement("div");
    notices.className = "civic-explore-notices";
    box.append(notices);
    const input = search.querySelector("input"), clear = search.querySelector(".civic-explore-clear");
    const list = search.querySelector("ul"), status = search.querySelector(".civic-explore-status");
    const select = box.querySelector("select"), checkbox = box.querySelector("details input");

    function say(text, kind) {
      status.replaceChildren();
      status.hidden = !text;
      status.dataset.kind = text ? kind || "" : "";
      if (!text) return;
      status.append(text);
      if (kind === "error") {
        const retry = document.createElement("button");
        retry.type = "button"; retry.className = "civic-explore-retry"; retry.textContent = "Повторить";
        retry.addEventListener("click", () => { say("Загружаем список улиц…", "loading"); loadIndex(); });
        status.append(" ", retry);
      }
    }

    // Clears transient messages but keeps "index unavailable" (and its retry) until the index loads.
    function quiet() { if (index.state !== "error") say(""); }

    // ---- street index: loading / ready / error (with retry)
    let index = { state: "loading", items: [] };
    let controller = null;
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
        const snapshot = String(data.source?.snapshot_at || "").slice(0, 10);
        index = { state: "ready", items: labelStreets(data.streets, features) };
        input.title = "Названия улиц из OpenStreetMap" + (snapshot ? " на " + snapshot : "") + ". Поиск по улицам, без номеров домов.";
        if (status.dataset.kind === "loading") say("");
        if (input.value.trim().length > 1 && document.activeElement === input) refresh();
      }).catch((e) => {
        if (destroyed || e.name === "AbortError") return;
        index = { state: "error", items: [] };
        close();
        say("Поиск улиц недоступен: список улиц не загрузился. Выберите район или повторите.", "error");
      });
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
      el.title = "Примерное место: центр участка улицы по OpenStreetMap";
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
        more.textContent = `Ещё ${matches.length - options.length} — уточните название`;
        list.append(more);
      }
      list.hidden = !options.length;
      input.setAttribute("aria-expanded", String(!!options.length));
      active = -1; input.removeAttribute("aria-activedescendant");
    }
    function refresh() {
      clear.hidden = !input.value;
      const q = input.value.trim();
      if (normalize(q).length < 2) { close(); quiet(); return; }
      if (index.state === "loading") { close(); say("Загружаем список улиц…", "loading"); return; }
      if (index.state === "error") { close(); return; }
      const matches = matchStreets(index.items, q);
      render(matches);
      if (!matches.length) say("Улица не найдена в снимке OpenStreetMap. Проверьте написание или выберите район.", "none");
      else if (matches.length > 1 && matches.some((m) => m.ambiguous)) say(`Найдено вариантов: ${matches.length}. Одноимённые улицы подписаны районом.`, "count");
      else say("");
    }
    function choose(it) {
      input.value = it.name; clear.hidden = false;
      close();
      selected = ""; select.value = ""; paint();
      say(`Показана улица: ${it.name} (${it.place}). Список записей — по видимой части карты.`, "chosen");
      pinStreet(it);
      onStreet?.({ name: it.name, label: it.label, place: it.place, district: it.district, bbox: it.bbox });
    }
    input.addEventListener("input", refresh);
    input.addEventListener("focus", () => { if (input.value.trim().length > 1 && index.state === "ready" && status.dataset.kind !== "chosen") refresh(); });
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
      if (index.state === "loading") { say("Загружаем список улиц…", "loading"); return; }
      if (index.state === "error") return;
      const matches = matchStreets(index.items, q);
      const exact = matches.filter((m) => m.norm === normalize(q));
      if (matches.length === 1 || exact.length === 1) { choose(exact.length === 1 ? exact[0] : matches[0]); return; }
      render(matches);
      if (matches.length) { highlight(0); say(`Найдено вариантов: ${matches.length}. Выберите стрелками и Enter или касанием.`, "count"); input.focus(); }
      else say("Улица не найдена в снимке OpenStreetMap. Проверьте написание или выберите район.", "none");
    });
    clear.addEventListener("click", () => { input.value = ""; unpin(); refresh(); input.focus(); });

    // ---- districts
    features.forEach((f) => {
      const option = document.createElement("option");
      option.value = f.properties.id; option.textContent = f.properties.name;
      select.append(option);
    });
    function paint() {
      if (destroyed || !map || !map.getStyle()?.layers) return;
      if (!map.getSource(PREFIX + "districts")) map.addSource(PREFIX + "districts", { type: "geojson", data: { type: "FeatureCollection", features } });
      if (!map.getLayer(PREFIX + "lines")) {
        const before = map.getStyle().layers.find((l) => l.type === "symbol")?.id;
        map.addLayer({ id: PREFIX + "lines", type: "line", source: PREFIX + "districts", paint: {
          "line-color": "#39745f", "line-width": 1.5, "line-opacity": 0.65, "line-dasharray": [3, 2],
        } }, before);
        map.addLayer({ id: PREFIX + "selected", type: "line", source: PREFIX + "districts", paint: {
          "line-color": "#246c51", "line-width": 3,
        }, filter: ["==", ["get", "id"], selected] }, before);
      }
      map.setLayoutProperty(PREFIX + "lines", "visibility", checkbox.checked ? "visible" : "none");
      map.setFilter(PREFIX + "selected", ["==", ["get", "id"], selected]);
    }
    select.addEventListener("change", () => {
      selected = select.value;
      input.value = ""; clear.hidden = true; close(); quiet(); unpin();
      paint();
      onNavigate(features.find((f) => f.properties.id === selected) || null);
    });
    checkbox.addEventListener("change", paint);
    box.querySelector(".civic-explore-objects").addEventListener("click", onObjects);
    map?.on("style.load", paint);
    paint();
    loadIndex();
    return {
      noticeSlot: notices,
      reset() { selected = ""; select.value = ""; input.value = ""; clear.hidden = true; close(); quiet(); unpin(); paint(); },
      updateRecords(items) {
        const demo = items.filter((x) => x.evidence === "synthetic").length;
        box.querySelector(".civic-explore-count").textContent = `Опубликовано записей: ${items.length}. Из них демонстрационных: ${demo}.`;
      },
      destroy() {
        destroyed = true; controller?.abort(); unpin(); map?.off("style.load", paint);
        for (const id of [PREFIX + "selected", PREFIX + "lines"]) if (map?.getLayer(id)) map.removeLayer(id);
        if (map?.getSource(PREFIX + "districts")) map.removeSource(PREFIX + "districts");
        box.remove();
      },
    };
  }
  global.CivicExplore = { mount, bounds, normalize, labelStreets, matchStreets, districtAt };
  if (typeof module !== "undefined") module.exports = { bounds, normalize, labelStreets, matchStreets, districtAt };
})(typeof window !== "undefined" ? window : globalThis);
