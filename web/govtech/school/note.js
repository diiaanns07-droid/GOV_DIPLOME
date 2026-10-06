/* Decision note of the school case: one self-contained HTML file built only from the current case and its comparison.
 * The case inputs are embedded (application/json) so that the note can be loaded back and give the same numbers.
 * Browser: window.SCHOOL_NOTE; Node: module.exports. No network, no scripts inside the note.
 */
(function (root) {
  "use strict";
  const esc = (v) => String(v).replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]);
  const m = (mm) => (mm === null || mm === undefined ? "нет данных" : Math.round(mm / 1000).toLocaleString("ru-RU") + " м");
  const METHOD = { geodesic: "по прямой (haversine) — не маршрут", "pedestrian-v1-strict": "маршрут по пешеходным рёбрам OSM/Overture (не проверено на месте)",
    "pedestrian-v1-exploratory": "маршрут по неполным данным (не гарантированно доступный пешеходный путь)" };
  const MARK_START = "school-access-case-embedded";

  /* buildNote(c, cmp, o) — c: case (school-access-case-v1 + BUILD extensions), cmp: compareCase(c, matrix),
   * o: {caseText (SCHOOL_CASE.exportCase(c)), cityLabel, label(target) → display name, verdict {code,winner}, generatedAt} */
  function buildNote(c, cmp, o) {
    if (!cmp || cmp.case_digest !== JSON.parse(o.caseText).case_digest) throw new Error("note: результат не соответствует кейсу");
    const plans = ["current", "A", "B"].map((id) => cmp.plans.find((p) => p.id === id)).filter(Boolean);
    const methodKey = c.parameters.distance_method === "geodesic" ? "geodesic" : c.parameters.routing_policy_id;
    const head = (p) => (p.id === "current" ? "Сейчас" : `Вариант ${p.id}: ${esc(o.label(c.candidates.find((k) => k.id === p.selected_candidate_ids[0])))}`);
    const rows = [["Среднее до ближайшей школы (известные точки)", (p) => m(p.metrics.mean_distance_mm)],
      [`В пределах ${c.parameters.threshold_m} м (параметр, не норматив)`, (p) => `${p.metrics.within_threshold_count} из ${p.metrics.total_origins}`],
      ["Самая дальняя точка", (p) => m(p.metrics.max_distance_mm)], ["Стало ближе", (p) => (p.id === "current" ? "—" : String(p.closer_count))],
      ["Неизвестно (не 0)", (p) => String(p.metrics.unknown_count)]];
    const v = o.verdict;
    const verdict = !v ? "Выбрано одно место: сравнение A/B не выполнялось." : v.code === "better" ? `По правилу (меньше неизвестных → меньше сумма расстояний → меньше самое дальнее) лучше вариант ${v.winner}.`
      : v.code === "tie" ? "По правилу варианты равны." : v.code === "no_gain" ? "Ни A, ни B не сокращают расстояния." : "Сравнение неполно.";
    const elig = cmp.eligible_school_ids.length, nf = c.sources.filter((s) => s.verification_status === "not_fetched").length;
    const srcRows = c.sources.map((s) => `<tr><td>${esc(s.id)}</td><td>${esc(s.title || s.url || "")}</td><td>${esc(s.verification_status)}</td><td>${esc(s.data_period || s.published_at || "нет данных")}</td></tr>`).join("");
    const limits = ["Расстояние: " + METHOD[methodKey] + ". Это не время в пути.", "Точки анализа — сетка с равными весами: не жители, не дети, не дома. Доля — от всех точек, не от населения.",
      "Вместимость школ и допуск к приёму неизвестны: ближе — не значит, что есть места.", "Школы за рамкой участка не загружены: у края расстояния могут быть завышены.",
      "Места A/B — гипотезы: свободен ли участок, стоимость и возможность строительства не проверены. Бюджета в расчёте нет.",
      "Данные о школах вторичные (Overture/OSM); официальный перечень не сверялся" + (nf ? ` (${nf} источников не открыты, NOT_FETCHED)` : "") + "."];
    const json = o.caseText.replace(/</g, "\\u003c");
    return `<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Записка: доступность школ — ${esc(o.cityLabel)}</title>
<style>body{font:14px/1.55 "Segoe UI",Inter,Arial,sans-serif;color:#152c26;background:#f7f8f4;margin:0;padding:24px}main{max-width:820px;margin:auto;background:#fff;border:1px solid #e4e9e3;border-radius:16px;padding:24px 28px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:22px 0 8px}table{border-collapse:collapse;width:100%;font-size:13px}th,td{border-bottom:1px solid #e4e9e3;padding:6px;text-align:left;vertical-align:top}
.muted{color:#6d7c76}.tag{display:inline-block;font-size:11px;font-weight:700;color:#176b4a;text-transform:uppercase;letter-spacing:.05em}code{font-size:12px;word-break:break-all}</style></head>
<body><main>
<span class="tag">Записка по расчёту · ${esc(o.cityLabel)}</span>
<h1>${esc(c.title)}</h1>
<p class="muted">Сформировано ${esc(o.generatedAt)} в «Городской лаборатории» (основной сайт). Все числа — из расчёта по входам ниже; текст собран по шаблону, не AI.</p>
<h2>Вопрос</h2><p>Какие точки участка дальше от известных школ и какое из мест A или B лучше меняет доступность? Это анализ пространственной доступности, не расчёт дефицита мест и не решение о выделении земли.</p>
<h2>Вывод</h2><p><b>${esc(verdict)}</b></p>
<table><tr><th></th>${plans.map((p) => `<th>${head(p)}</th>`).join("")}</tr>
${rows.map(([n, f]) => `<tr><th>${esc(n)}</th>${plans.map((p) => `<td>${esc(f(p))}</td>`).join("")}</tr>`).join("\n")}</table>
<h2>Как считалось</h2><ul><li>Расстояние: ${esc(METHOD[methodKey])}${cmp.graph_sha256 ? ` (граф K03 <code>${esc(cmp.graph_sha256.slice(0, 16))}…</code>, © OpenStreetMap contributors, ODbL-1.0)` : ""}.</li>
<li>Школ в расчёте: ${elig} из ${c.schools.length} в кейсе; правило: ${esc(c.parameters.target_policy.id)}.</li>
<li>Точек анализа: ${c.origins.length}; мест для сравнения: ${c.candidates.length}; стоимость мест: нет данных.</li>
<li>Для каждой точки — ближайшая школа сейчас и с выбранным местом; изменение = после − до; неизвестное не считается нулём.</li></ul>
<h2>Источники</h2><table><tr><th>ID</th><th>Источник</th><th>Статус</th><th>Период</th></tr>${srcRows}</table>
<h2>Чего этот расчёт не говорит</h2><ul>${limits.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>
<h2>Воспроизведение</h2><p>case_digest <code>${esc(cmp.case_digest)}</code>; снимок <code>${esc(c.snapshot_id)}</code>.<br>
Откройте сайт → «Городское планирование» → «Загрузить кейс…» и выберите этот файл: входы будут проверены, числа пересчитаны.</p>
<p class="muted">Проверка людьми и на месте не проводилась.</p>
<script type="application/json" id="${MARK_START}">${json}</script>
</main></body></html>
`;
  }
  /* extractCase(html) → the embedded case JSON text, or null when the note has none. */
  function extractCase(html) {
    const mm = new RegExp('<script type="application/json" id="' + MARK_START + '">([\\s\\S]*?)</script>').exec(String(html));
    return mm ? mm[1] : null;
  }
  const api = { buildNote, extractCase };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.SCHOOL_NOTE = api;
})(typeof window !== "undefined" ? window : globalThis);
