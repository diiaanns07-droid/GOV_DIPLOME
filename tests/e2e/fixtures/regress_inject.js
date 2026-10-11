// R10 · отрицательный контроль для compare_baseline.cjs (не приёмка): имитирует то, от чего защищает правило 7
// POLISH_WAVE_2.md, — «новая функция» добавила слой, видимый по умолчанию, свои значки поверх карты и замедлила
// тепловую карту на 1.5 с. Подключается так: map_baseline.cjs --inject-js tests/e2e/fixtures/regress_inject.js
// Сравнение с эталоном 8e67c65 обязано дать «ХУЖЕ» (новый слой, новый вид значков, медленнее первый значок).
(function () {
  "use strict";
  var realFetch = window.fetch;
  window.fetch = function (input, init) {
    var url = typeof input === "string" ? input : (input && input.url) || "";
    if (/\/api\/civic\/v2\/heat(\?|$)/.test(url)) {
      return new Promise(function (ok) { setTimeout(ok, 1500); }).then(function () { return realFetch(input, init); });
    }
    return realFetch(input, init);
  };
  var tries = 0;
  var timer = setInterval(function () {
    tries++;
    // eslint-disable-next-line no-undef
    var m = typeof map !== "undefined" && map && map.getStyle ? map : null;
    if (!m || !m.isStyleLoaded() || !window.maplibregl) { if (tries > 300) clearInterval(timer); return; }
    clearInterval(timer);
    var pts = [];
    for (var i = 0; i < 40; i++) pts.push({ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: [71.33 + (i % 8) * 0.025, 51.08 + Math.floor(i / 8) * 0.02] } });
    m.addSource("r10-fake-nearby", { type: "geojson", data: { type: "FeatureCollection", features: pts } });
    m.addLayer({ id: "r10-fake-nearby", type: "circle", source: "r10-fake-nearby", paint: { "circle-radius": 9, "circle-color": "#7a3cff", "circle-opacity": 0.85 } });
    for (var j = 0; j < 6; j++) {
      var el = document.createElement("div");
      el.className = "r10-fake-pin";
      el.textContent = "Рядом " + (j + 1);
      el.style.cssText = "background:#7a3cff;color:#fff;padding:4px 8px;border-radius:12px;font:14px sans-serif";
      new window.maplibregl.Marker({ element: el }).setLngLat([71.40 + j * 0.02, 51.12 + (j % 3) * 0.015]).addTo(m);
    }
  }, 50);
})();
