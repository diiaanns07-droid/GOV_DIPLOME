/* City navigation uses the existing OSM boundaries; it never changes training scores. */
(function (global) {
  "use strict";
  const PREFIX = "civic-explore-";
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
  function mount({ root, map, districts, onNavigate, onObjects, onStreet }) {
    const features = (districts?.features || []).filter((f) => bounds(f.geometry));
    let selected = "", destroyed = false;
    const box = document.createElement("section");
    box.className = "civic-explore";
    box.setAttribute("aria-label", "Навигация по Астане");
    box.innerHTML = `<div class="civic-explore-row"><label><span>Территория</span><select aria-label="Район Астаны"><option value="">Вся Астана</option></select></label><button type="button" class="civic-explore-objects">К объектам</button><details><summary aria-label="Покрытие и слои карты">Слои</summary><div class="civic-explore-details"><label><input type="checkbox"> Границы районов</label><p>Карта доступна по всей Астане. Пустое место означает отсутствие опубликованных записей, а не отсутствие работ.</p><p class="civic-explore-count" role="status"></p><p>Границы: OpenStreetMap, снимок 23.09.2026. Это общественная карта, не кадастровые границы.</p></div></details></div>`;
    root.append(box);
    const search = document.createElement("form");
    search.className = "civic-explore-search";
    search.innerHTML = `<input type="search" placeholder="Найти улицу в Астане" aria-label="Найти улицу в Астане" list="civic-explore-streets" autocomplete="off"><datalist id="civic-explore-streets"></datalist><button type="submit">Найти</button><span role="status" hidden></span>`;
    box.append(search);
    const input = search.querySelector("input"), status = search.querySelector("span"), datalist = search.querySelector("datalist");
    let streets = null;
    const controller = new AbortController();
    fetch("/civic/map/streets.json", { signal: controller.signal }).then((r) => {
      if (!r.ok) throw new Error("street index unavailable");
      return r.json();
    }).then((data) => {
      if (destroyed) return;
      streets = data.streets;
      input.title = "Названия из OpenStreetMap на " + data.source.snapshot_at.slice(0, 10) + ". Поиск по улицам, без номеров домов.";
    }).catch((e) => { if (!destroyed && e.name !== "AbortError") { status.hidden = false; status.textContent = "Поиск улиц недоступен. Выберите район."; } });
    input.addEventListener("input", () => {
      status.hidden = true;
      const q = input.value.trim().toLocaleLowerCase("ru");
      datalist.replaceChildren(...(q.length > 1 ? (streets || []).filter((s) => s.name.toLocaleLowerCase("ru").includes(q)).slice(0, 12) : []).map((s) => {
        const o = document.createElement("option"); o.value = s.label || s.name; return o;
      }));
    });
    search.addEventListener("submit", (event) => {
      event.preventDefault();
      const q = input.value.trim().toLocaleLowerCase("ru");
      const matches = q ? (streets || []).filter((s) => (s.label || s.name).toLocaleLowerCase("ru").includes(q)) : [];
      const street = matches.find((s) => (s.label || s.name).toLocaleLowerCase("ru") === q) || (matches.length === 1 ? matches[0] : null);
      if (!street) {
        status.hidden = false;
        status.textContent = streets === null ? "Список улиц ещё загружается." : matches.length ? "Уточните название или выберите улицу из подсказок." : "Улица не найдена в снимке OSM. Попробуйте другое название или выберите район.";
        return;
      }
      selected = ""; select.value = ""; paint(); status.hidden = true;
      input.value = street.label || street.name; onStreet(street);
    });
    const select = box.querySelector("select"), checkbox = box.querySelector("input");
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
      input.value = ""; datalist.replaceChildren(); status.hidden = true;
      paint();
      onNavigate(features.find((f) => f.properties.id === selected) || null);
    });
    checkbox.addEventListener("change", paint);
    box.querySelector("button").addEventListener("click", onObjects);
    map?.on("style.load", paint);
    paint();
    return {
      reset() { selected = ""; select.value = ""; input.value = ""; datalist.replaceChildren(); status.hidden = true; paint(); },
      updateRecords(items) {
        const demo = items.filter((x) => x.evidence === "synthetic").length;
        box.querySelector(".civic-explore-count").textContent = `Опубликовано записей: ${items.length}. Из них демонстрационных: ${demo}.`;
      },
      destroy() {
        destroyed = true; controller.abort(); map?.off("style.load", paint);
        for (const id of [PREFIX + "selected", PREFIX + "lines"]) if (map?.getLayer(id)) map.removeLayer(id);
        if (map?.getSource(PREFIX + "districts")) map.removeSource(PREFIX + "districts");
        box.remove();
      },
    };
  }
  global.CivicExplore = { mount, bounds };
  if (typeof module !== "undefined") module.exports = { bounds };
})(typeof window !== "undefined" ? window : globalThis);
