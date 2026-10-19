// Пробное применение GLASS.md §4 R01 №1–7 (только классы) — самопроверка R10, не код R01.
(() => {
  const RULES = [
    ["#birge-header", ["bk-glass", "bk-glass--bar"]],
    ["#birge-account, .birge-more-menu, #birge-layer", ["bk-glass"]],
    ["#birge-locate, #toggle-3d, #birge-layer-btn, #birge-compass, .bk-mapctl__group, .birge-legend-line button", ["bk-glass--control"]],
    [".birge-legend-line", ["bk-glass", "bk-glass--bar"]],
    ["#civic-panel", ["bk-glass"]],
    ["#birge-screen, #birge-day", ["bk-glass"]],
    ["#map-status", ["bk-glass", "bk-glass--bar"]],
  ];
  const apply = () => {
    for (const [sel, cls] of RULES) for (const e of document.querySelectorAll(sel)) for (const c of cls) if (!e.classList.contains(c)) e.classList.add(c);
    const p = document.getElementById("civic-panel");
    if (p) p.classList.toggle("bk-glass--sheet", innerWidth < 761);
  };
  const start = () => { apply(); new MutationObserver(apply).observe(document.body, { childList: true, subtree: true }); };
  if (document.body) start(); else document.addEventListener("DOMContentLoaded", start);
})();
