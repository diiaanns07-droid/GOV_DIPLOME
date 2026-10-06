"""K03 r10: предложение BUILD — подключить pedestrian-v1 к school-access-case-v1 сборки (case.js) и раздать модуль K03.

  python3 research/round-10-results/K03/make_build_patch.py --base <распакованное дерево BUILD c0b276e> --out <дерево с изменениями>
     → patches/build_c0b276e_k03_pedestrian.patch (unified diff относительно --base)

Изменения (только текстовые правки, повторяемые этим скриптом; общий сайт K03 не трогает):
  ui/web_server.py              + 5 файлов web/govtech/k03/ в явном белом списке;
  web/index.html                + <script> k03/routing.js, k03/school-access-routing.js перед school/case.js;
  web/govtech/school/case.js    distance_method pedestrian-v1 только с routing_policy_id (strict|exploratory) и routing_snapshot
                                {graph_sha256, policy_sha256, max_snap_m} → входит в case_digest; матрица другого графа/политики →
                                matrix_snapshot; допущения и ограничения зависят от метода (не «прямая» для маршрута); строка плана
                                считает цели без известного расстояния (unknown_targets) → ограничение targets_with_unknown_distance;
  tests/govtech/school_case.cjs устаревшая проверка «pedestrian не подключён» → «pedestrian без политики/отпечатка» (+ неизвестный метод);
  tests/govtech/school_pedestrian.cjs  новый тест: compareCase сборки на матрице K03 = независимый перебор по строкам матрицы;
  tests/test_k03_routing_assets.py     хэши web/govtech/k03 = K03_MANIFEST.json.
Файлы web/govtech/k03/* ставит install_for_build.py (графы ~3 МБ в патч не входят).
"""
import argparse
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent


def edit(path, old, new, count=1):
    s = path.read_text(encoding='utf-8')
    if s.count(old) != count:
        raise SystemExit(f'{path}: фрагмент найден {s.count(old)} раз, ожидалось {count}: {old[:60]!r}')
    path.write_text(s.replace(old, new), encoding='utf-8')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    if a.out.exists():
        shutil.rmtree(a.out)
    shutil.copytree(a.base, a.out)
    o = a.out
    edit(o / 'ui/web_server.py', '''               "school/case.js", "school/school-ui.js", "school/school.css"):''',
         '''               "school/case.js", "school/school-ui.js", "school/school.css",
               # K03 r10: пешеходные расстояния pedestrian-v1 (модуль, граф ODbL, манифест хэшей)
               "k03/routing.js", "k03/school-access-routing.js", "k03/shymkent.graph.json", "k03/astana.graph.json",
               "k03/K03_MANIFEST.json"):''')
    edit(o / 'web/index.html', '''    <script defer src="/govtech/school/case.js"></script>
''', '''    <script defer src="/govtech/k03/routing.js"></script>
    <script defer src="/govtech/k03/school-access-routing.js"></script>
    <script defer src="/govtech/school/case.js"></script>
''')
    cj = o / 'web/govtech/school/case.js'
    edit(cj, '''  const GEODESIC = "geodesic";
''', '''  const GEODESIC = "geodesic";
  const PEDESTRIAN = "pedestrian-v1";  // K03 r10: web/govtech/k03/routing.js
  const ROUTING_POLICIES = ["pedestrian-v1-strict", "pedestrian-v1-exploratory"];
''')
    edit(cj, '''    if (p.distance_method !== GEODESIC) fail("method", "в этой сборке доступен только geodesic (по прямой); pedestrian-v1 не подключён");
    if (p.routing_policy_id !== null) fail("policy", "для прямой routing_policy_id = null");
''', '''    // pedestrian-v1 — только с отпечатком графа и политики K03; он входит в case_digest через parameters
    if (p.distance_method === GEODESIC) {
      if (p.routing_policy_id !== null) fail("policy", "для прямой routing_policy_id = null");
      if ("routing_snapshot" in p) fail("policy", "для прямой routing_snapshot не задаётся");
    } else if (p.distance_method === PEDESTRIAN) {
      if (!ROUTING_POLICIES.includes(p.routing_policy_id)) fail("policy", "routing_policy_id: " + ROUTING_POLICIES.join(" | "));
      const rs = p.routing_snapshot;
      if (!rs || typeof rs !== "object" || !/^[0-9a-f]{64}$/.test(rs.graph_sha256 || "") || !/^[0-9a-f]{64}$/.test(rs.policy_sha256 || "") || !isInt(rs.max_snap_m))
        fail("routing_snapshot", "pedestrian-v1 требует routing_snapshot {graph_sha256, policy_sha256, max_snap_m} графа K03");
    } else fail("method", "distance_method: geodesic | pedestrian-v1");
''')
    edit(cj, '''    if (mx.method !== c.parameters.distance_method) fail("matrix_method", "метод матрицы не совпадает с кейсом");
''', '''    if (mx.method !== c.parameters.distance_method) fail("matrix_method", "метод матрицы не совпадает с кейсом");
    if (mx.method === PEDESTRIAN) {
      const rs = c.parameters.routing_snapshot;
      if (mx.policy_id !== c.parameters.routing_policy_id || mx.graph_sha256 !== rs.graph_sha256 || mx.policy_sha256 !== rs.policy_sha256)
        fail("matrix_snapshot", "матрица построена на другом графе или политике, чем кейс");
    }
''')
    edit(cj, '''      const b = nearestOf(index, o.id, eligible), a = nearestOf(index, o.id, [...eligible, ...extra]);
      return { origin_id: o.id, before_mm: b ? b.mm : null, after_mm: a ? a.mm : null, delta_mm: a && b ? a.mm - b.mm : null,
        status: a ? "ok" : "unknown", nearest_target_id: a ? a.t.id : null, source_ids: a ? a.t.source_ids.slice() : [] };''',
         '''      const b = nearestOf(index, o.id, eligible), a = nearestOf(index, o.id, [...eligible, ...extra]);
      // цели без известного расстояния (маршрут не найден/не подтверждён): минимум — только по известным, неполнота видна
      const unknownTargets = [...eligible, ...extra].filter((t) => { const r = index.get(o.id + "\\u0000" + t.id); return !r || r.status !== "ok"; }).length;
      return { origin_id: o.id, before_mm: b ? b.mm : null, after_mm: a ? a.mm : null, delta_mm: a && b ? a.mm - b.mm : null,
        status: a ? "ok" : "unknown", nearest_target_id: a ? a.t.id : null, source_ids: a ? a.t.source_ids.slice() : [], unknown_targets: unknownTargets };''')
    edit(cj, '''    if (metrics.unknown_count) limitations.push("unknown_distances");
''', '''    if (metrics.unknown_count) limitations.push("unknown_distances");
    if (rows.some((r) => r.unknown_targets)) limitations.push("targets_with_unknown_distance");
''')
    edit(cj, '''    const facts = [];
    const fact = ''', '''    const methodNote = mx.method === GEODESIC ? "straight_line_not_route"
      : mx.policy_id === "pedestrian-v1-strict" ? "pedestrian_route_osm_not_field_checked" : "pedestrian_route_incomplete_data";
    const facts = [];
    const fact = ''')
    edit(cj, '''      assumptions: ["straight_line_not_route", ...(extraAssumptions || [])] });''',
         '''      assumptions: [methodNote, ...(extraAssumptions || [])] });''')
    edit(cj, '''    const limitations = ["straight_line_not_route", "schools_outside_slice_not_loaded",''',
         '''    const limitations = [methodNote, ...(mx.method === PEDESTRIAN ? ["routing_slice_boundary_unverified", "snap_model_connection"] : []), "schools_outside_slice_not_loaded",''')
    edit(cj, '''  const api = { SCHEMA, COMPARE_SCHEMA, CANON, METRIC, LIMITS, TARGET_POLICY, SCHOOL_CATEGORIES, CaseError,''',
         '''  const api = { SCHEMA, COMPARE_SCHEMA, CANON, METRIC, LIMITS, TARGET_POLICY, SCHOOL_CATEGORIES, PEDESTRIAN, ROUTING_POLICIES, CaseError,''')
    edit(o / 'tests/govtech/school_case.cjs', '''  bad((c) => { c.parameters.distance_method = "pedestrian-v1"; }, "method", "pedestrian not connected");''',
         '''  bad((c) => { c.parameters.distance_method = "pedestrian-v1"; }, "policy", "pedestrian-v1 without routing policy/snapshot");
  bad((c) => { c.parameters.distance_method = "walking"; }, "method", "unknown distance method");''')
    shutil.copyfile(HERE / 'build_tests/school_pedestrian.cjs', o / 'tests/govtech/school_pedestrian.cjs')
    shutil.copyfile(HERE / 'build_tests/test_k03_routing_assets.py', o / 'tests/test_k03_routing_assets.py')
    patch = HERE / 'patches/build_c0b276e_k03_pedestrian.patch'
    with patch.open('w', encoding='utf-8') as fh:
        for rel in ('ui/web_server.py', 'web/index.html', 'web/govtech/school/case.js', 'tests/govtech/school_case.cjs',
                    'tests/govtech/school_pedestrian.cjs', 'tests/test_k03_routing_assets.py'):
            old = a.base / rel
            r = subprocess.run(['diff', '-uN', '--label', f'a/{rel}', '--label', f'b/{rel}', str(old) if old.exists() else '/dev/null', str(o / rel)],
                               capture_output=True, text=True)
            fh.write(r.stdout)
    print('patch:', patch, sum(1 for _ in patch.open(encoding='utf-8')), 'строк')


if __name__ == '__main__':
    main()
