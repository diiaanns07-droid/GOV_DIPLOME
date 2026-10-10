/* Local-first basemap. No remote requests when the installed archive is usable. */
(function () {
  "use strict";
  const BASE = "/civic/offline/";
  let active = false, reason = "not-started", protocol;
  const names = (lang) => lang === "kk"
    ? ["coalesce", ["get", "name:kk"], ["get", "name"], ["get", "name:ru"], ""]
    : ["coalesce", ["get", "name:ru"], ["get", "name"], ["get", "name:kk"], ""];
  function labels(map, lang) {
    if (!active) return;
    for (const layer of map.getStyle().layers) {
      if (layer.id.startsWith("offline-label-")) map.setLayoutProperty(layer.id, "text-field", names(lang));
    }
  }
  async function choose(online) {
    const forced = new URLSearchParams(location.search).get("offline") === "1" || !navigator.onLine;
    try {
      const res = await fetch(BASE + "status.json", { cache: "no-store", signal: AbortSignal.timeout(2500) });
      if (!res.ok || !(await res.json()).available) throw new Error("archive-missing");
      const styleResponse = await fetch(BASE + "style.json");
      if (!styleResponse.ok) throw new Error("style-missing");
      const style = await styleResponse.json();
      if (!window.pmtiles) throw new Error("pmtiles-library-missing");
      if (!protocol) {
        protocol = new pmtiles.Protocol();
        maplibregl.addProtocol("pmtiles", protocol.tile);
      }
      style.sources.protomaps.url = "pmtiles://" + new URL(BASE + "astana.pmtiles", location.href).href;
      style.glyphs = new URL(BASE + "fonts/{fontstack}/{range}.pbf", location.href).href.replaceAll("%7B", "{").replaceAll("%7D", "}");
      style.sprite = new URL(BASE + "sprites/v4/light", location.href).href;
      const lang = document.documentElement.lang === "kk" ? "kk" : "ru";
      for (const layer of style.layers) if (layer.id.startsWith("offline-label-")) layer.layout["text-field"] = names(lang);
      active = true;
      reason = forced ? "forced-or-network-offline" : "installed-local-first";
      document.documentElement.dataset.basemap = "offline-pmtiles";
      return { style, schematic: false };
    } catch (error) {
      reason = String(error.message || error);
      return { style: forced ? null : online, schematic: forced };
    }
  }
  function buildingLayer() {
    // Protomaps computes height from OSM height/building:levels upstream.
    // Floors fallback also supports future/local tiles retaining raw OSM tags.
    const height = ["max", 1, ["coalesce", ["get", "height"], ["*", 3, ["to-number", ["get", "building:levels"], 2]]]];
    return { id: "akim-3d", type: "fill-extrusion", source: "protomaps", "source-layer": "buildings", minzoom: 14,
      filter: ["in", ["get", "kind"], ["literal", ["building", "building_part"]]],
      paint: {
        "fill-extrusion-color": ["interpolate", ["linear"], height, 0, "#e1e6d9", 60, "#b7c9a2", 180, "#87a489"],
        "fill-extrusion-height": ["interpolate", ["linear"], ["zoom"], 14, 0, 15.4, height],
        "fill-extrusion-base": ["coalesce", ["get", "min_height"], 0],
        "fill-extrusion-opacity": 0.92
      }
    };
  }
  function attach(map) {
    if (!active) return;
    labels(map, document.documentElement.lang);
    window.addEventListener("birge:lang", event => labels(map, event.detail.lang));
  }
  window.BirgeOffline = { choose, buildingLayer, attach, names,
    get active() { return active; }, state: () => ({ active, reason }) };
})();
