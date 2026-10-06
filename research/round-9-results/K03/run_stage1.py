"""K03 r9, этап 1: r8 geo-fixtures и независимый оракул K03 против НАСТОЯЩЕГО web/plan.js сборки.

  python3 research/round-9-results/K03/run_stage1.py --app-root <копия prototypes/city-evidence> --target-sha <SHA> [--json out]

Что проверяется (через plan_adapter.cjs, без DOM):
  S1-build              хэши файлов сборки (для отчёта) и совпадение data.js/evidence.js с fixtures (иначе TEST_INCOMPATIBLE);
  S1-validate           все validate-случаи r8 (этапы 1–2): принять/отклонить как в r8; код — по таблице CODE_MAP (различия политики
                        перечислены, эталон r8 не меняется по ответу сборки);
  S1-context            bbox, набор записей категории и source_snapshot plan.js = независимый пересчёт по формуле plan.js;
  S1-nearest-fixtures   table/after/bind-случаи r8: ближайшая запись (ID, мм), мм до кандидатов, after/delta = оракул r8;
  S1-real-sources       точка в координатах каждой настоящей записи: 0 мм, меньший ID в ничьей, кандидат поверх записи не побеждает;
  S1-random             seeded synthetic сценарии: все строки evaluatePlan = оракул;
  S1-ties               ничьи: plan.js выбирает меньший ID из множества оракула; что из ничьи видно пользователю;
  S1-qa                 facts.qaOf (то, что показывает интерфейс у ближайшей записи) = QA-флаги оракула по каждой записи категории;
  S1-coincident-not-duplicate  совпадение координат не означает дубликат: записи не сливаются, POSSIBLE_DUPLICATE — по адресу/имени,
                        тексты UI не называют совпадение координат дубликатом;
  S1-integrity          адаптер не изменил data.js/evidence.js и загруженный объект.
Код выхода 1 при FAIL/TEST_INCOMPATIBLE. Без node — NOT_RUN (не PASS).
"""
import argparse
import itertools
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from r9_common import (R, R8, OUT, rec, parse_js, sha256_file, build_hashes, u16, run_adapter, plan_snapshot,  # noqa: E402
                       summary_and_save)
from run_tests import revive  # noqa: E402  (r8: {"$num": "NaN"} → float)

# Код ошибки geo_v2 r8 → код plan.js (city-plan-v2 сборки). Значение 'same' — тот же код.
CODE_MAP = {'too_many_points': 'bad_points', 'too_many_candidates': 'too_many_candidates', 'outside_bbox': 'outside_bbox',
            'lon_lat_swapped': 'outside_bbox', 'other_city': 'outside_bbox', 'not_number': 'bad_coord', 'not_finite': 'bad_coord',
            'out_of_range': 'bad_coord', 'duplicate_id': 'duplicate_id', 'bad_id': 'bad_id', 'bad_weight': 'bad_weight',
            'bad_cost': 'bad_cost', 'bad_kind': 'bad_kind', 'bad_category': 'bad_category', 'bad_shape': 'bad_shape'}
POLICY = {
    'lon_lat_swapped': 'plan.js не распознаёт перестановку lon/lat у точки: отказ outside_bbox (верный отказ, менее точная подсказка)',
    'other_city': 'plan.js не называет город точки: отказ outside_bbox; other_city — только для city_id сценария',
    'not_number': 'plan.js объединяет нечисло, NaN/Infinity и диапазон в bad_coord',
    'not_finite': 'plan.js объединяет нечисло, NaN/Infinity и диапазон в bad_coord',
    'out_of_range': 'plan.js объединяет нечисло, NaN/Infinity и диапазон в bad_coord',
    'too_many_points': 'другое имя кода: bad_points',
}


def load_r8(app):
    docs = {s: json.loads((R8 / f'fixtures/stage{s}.json').read_text(encoding='utf-8')) for s in (1, 2, 3)}
    scan = json.loads((HERE / 'fixtures/stage1_scan.json').read_text(encoding='utf-8'))
    have = {'data_js_sha256': sha256_file(app / 'web/data.js'), 'evidence_js_sha256': sha256_file(app / 'web/evidence.js')}
    bad = {f'stage{s}' if s != 'scan' else 'stage1_scan': [k for k in have if d['target'].get(k) != have[k]]
           for s, d in list(docs.items()) + [('scan', scan)]}
    bad = {k: v for k, v in bad.items() if v}
    return docs, scan, have, bad


def oracle_case(data, ev, c, cache):
    """Оракул r8: валидированные места, таблица и after по выбранным ID (или None, если оракул отклоняет)."""
    k = (c['city'], c['category'])
    if k not in cache:
        cache[k] = R.build_context(data, ev, *k)
    ctx = cache[k]
    v = R.validate_places(ctx, revive(c['places']), allow_empty_points=bool(c.get('allow_empty')))
    t = R.distance_table(ctx, v['control_points'], v['candidates'])
    ids = [q['id'] for q in v['candidates']]
    sel = [ids.index(i) for i in c.get('selected_ids') or []]
    after = [R.nearest_after(t, i, sel, v['candidates']) for i in range(len(v['control_points']))]
    return ctx, v, t, after


def compare_rows(cid, v, t, after, pt, pa):
    """Сверка ответа plan.js (table pt, after pa) с оракулом; возвращает (ошибки, ничьи)."""
    errs, ties = [], []
    pids = [p['id'] for p in v['control_points']]
    rows = {r['id']: r for r in pa['rows']}
    for i, pid in enumerate(pids):
        b, pb, row = t['baseline'][i], pt['base'][pid], rows[pid]
        want = {'id': b['id'], 'mm': b['mm']} if b else None
        if pb != want:
            errs.append(f'{cid}/{pid}: base plan {pb} ≠ оракул {want}')
        if b and len(b['tied_keys']) > 1:
            ids = [k.split(':', 1)[1] for k in b['tied_keys']]
            ties.append({'case': cid, 'point': pid, 'plan_id': pb and pb['id'], 'tied_ids': ids, 'mm': b['mm']})
            if not pb or pb['id'] != min(ids, key=u16):
                errs.append(f'{cid}/{pid}: в ничьей {ids} plan выбрал {pb}, а не меньший ID')
        if row['before_mm'] != (b['mm'] if b else None) or row['nearest_before'] != ({'kind': 'source', 'id': b['id']} if b else None):
            errs.append(f'{cid}/{pid}: before строки {row["before_mm"]} {row["nearest_before"]} ≠ оракул')
        for j, q in enumerate(v['candidates']):
            if pt['dist'][q['id']][pid] != t['to_candidates'][i][j]:
                errs.append(f'{cid}/{pid}→{q["id"]}: {pt["dist"][q["id"]][pid]} мм ≠ оракул {t["to_candidates"][i][j]}')
        a = after[i]
        want_a = {'kind': a['kind'], 'id': a['key'].split(':', 1)[1]} if a else None
        if row['nearest_after'] != want_a or row['after_mm'] != (a['mm'] if a else None):
            errs.append(f'{cid}/{pid}: after plan {row["nearest_after"]} {row["after_mm"]} ≠ оракул {want_a} {a and a["mm"]}')
        want_d = b['mm'] - a['mm'] if b and a else None
        if row['delta_mm'] != want_d:
            errs.append(f'{cid}/{pid}: delta {row["delta_mm"]} ≠ {want_d}')
    return errs, ties


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--app-root', type=Path, required=True)
    ap.add_argument('--target-sha', required=True)
    ap.add_argument('--json', type=Path)
    a = ap.parse_args()
    app = a.app_root.resolve()
    hashes = build_hashes(app)
    docs, scan, have, bad = load_r8(app)
    if bad:
        rec('S1-build', 'TEST_INCOMPATIBLE', f'данные сборки {a.target_sha[:12]} ≠ данным fixtures: {bad}; пересоздать fixtures для этого SHA',
            target_sha=a.target_sha, web_sha256=hashes, mismatch=bad)
        return summary_and_save(a.json)
    rec('S1-build', 'PASS', f'сборка {a.target_sha[:12]}: data.js/evidence.js = данным fixtures r8 и scan', target_sha=a.target_sha,
        web_sha256=hashes, fixtures_r8_target=docs[1]['target']['sha'])
    data, ev = parse_js(app / 'web/data.js'), parse_js(app / 'web/evidence.js')

    # ---- запросы к адаптеру ----
    req = []
    val_cases = [c for s in (1, 2) for c in docs[s]['cases'] if c['op'] == 'validate']
    for c in val_cases:
        req.append(dict(id='V:' + c['id'], op='validate', city=c['city'], category=c['category'], places=c['places'],
                        allow_empty=bool(c.get('allow_empty'))))
    near = []
    for s in (1, 2, 3):
        for c in docs[s]['cases']:
            if c['op'] in ('table', 'after', 'bind', 'cand_evidence'):
                cands = c['places']['candidates']
                sel = [cands[j]['id'] for j in c.get('selected') or []]
                near.append(dict(id=c['id'], city=c['city'], category=c['category'], places=c['places'], selected_ids=sel, src=f'r8 stage{s}'))
    for c in scan['cases']:
        near.append(dict(id=c['id'], city=c['city'], category=c['category'], places=c['places'], selected_ids=c['selected_ids'],
                         src=c['kind'], expect=c.get('expect')))
    for c in near:
        req.append(dict(id='T:' + c['id'], op='table', city=c['city'], category=c['category'], places=c['places'], selected_ids=c['selected_ids']))
        req.append(dict(id='A:' + c['id'], op='after', city=c['city'], category=c['category'], places=c['places'], selected_ids=c['selected_ids']))
    for city in ('astana', 'shymkent'):
        req.append(dict(id='C:' + city, op='context', city=city))
        ids = [p['id'] for p in data['cities'][city]['places']]
        req.append(dict(id='Q:' + city, op='qa', city=city, ids=ids))
    res, integ = run_adapter(app, req)
    if res is None:
        rec('S1-plan-js', 'NOT_RUN', integ)
        return summary_and_save(a.json)
    crashes = [k for k, x in res.items() if x.get('crash')]
    if crashes:
        rec('S1-adapter', 'FAIL', f'исключения не PlanError: {len(crashes)}', crashes={k: res[k]['crash'] for k in crashes[:5]})

    # ---- S1-validate ----
    mism, policy, exact = [], {}, 0
    for c in val_cases:
        r, e = res['V:' + c['id']], c['expect']
        if r['ok'] != e['ok']:
            mism.append(f'{c["id"]}: plan ok={r["ok"]} {r.get("error")}, r8 ожидает {e}')
        elif not e['ok']:
            want = CODE_MAP[e['code']]
            if r['error']['code'] != want:
                mism.append(f'{c["id"]}: plan {r["error"]["code"]} ≠ {want} (r8 {e["code"]})')
            elif e['code'] == want:
                exact += 1
            else:
                policy.setdefault(e['code'], []).append(c['id'])
        else:
            exact += 1
    rec('S1-validate', 'FAIL' if mism else 'PASS',
        f'{len(val_cases)} validate-случаев r8 (этапы 1–2) на plan.validatePlanScenario: совпало решение принять/отклонить у всех, '
        f'тот же код {exact}, код по таблице политики {sum(map(len, policy.values()))}, несоответствий {len(mism)}',
        mismatches=mism[:20], policy_differences={k: {'cases': v, 'why': POLICY[k], 'plan_code': CODE_MAP[k]} for k, v in policy.items()},
        not_compared='путь ошибки: plan.js отдаёт только текст detail, поля path нет')

    # ---- S1-context ----
    errs, info = [], {}
    for city in ('astana', 'shymkent'):
        r = res['C:' + city]['result']
        snap = plan_snapshot(data, city)
        if r['source_snapshot'] != snap or r['snapshot_recomputed'] != snap:
            errs.append(f'{city}: source_snapshot plan {r["source_snapshot"]} ≠ независимый пересчёт {snap}')
        if r['bbox'] != data['cities'][city]['bbox']:
            errs.append(f'{city}: bbox')
        if not r['frozen']:
            errs.append(f'{city}: контекст plan.js не заморожен')
        for cat in ('school', 'outpatient_clinic'):
            octx = R.build_context(data, ev, city, cat)
            mine = sorted([s['id'], s['lon'], s['lat']] for s in octx['sources'])
            theirs = sorted([p[0], p[2], p[3]] for p in r['places'] if p[1] == cat)
            if mine != theirs:
                errs.append(f'{city}/{cat}: набор записей plan.js ≠ оракулу ({len(theirs)} vs {len(mine)})')
            if octx['bbox'] != r['bbox']:
                errs.append(f'{city}/{cat}: bbox оракула')
            info[f'{city}/{cat}'] = len(theirs)
        info[f'{city} snapshot plan.js'] = snap
        info[f'{city} snapshot geo_v2 r8 (другая формула, с bbox — не сравнивается побайтно)'] = R.build_context(data, ev, city, 'school')['source_snapshot']
    rec('S1-context', 'FAIL' if errs else 'PASS', f'контексты обоих городов: bbox, записи категорий и source_snapshot (независимый пересчёт формулы plan.js); ошибок {len(errs)}',
        errors=errs, records=info)

    # ---- S1-nearest-fixtures / real-sources / random / ties ----
    cache, groups, all_ties = {}, {'r8': [], 'real_sources': [], 'random': []}, []
    counts = {'r8': 0, 'real_sources': 0, 'random': 0}
    for c in near:
        g = 'r8' if c['src'].startswith('r8') else c['src']
        pt, pa = res['T:' + c['id']], res['A:' + c['id']]
        if not (pt['ok'] and pa['ok']):
            groups[g].append(f'{c["id"]}: plan.js отклонил сценарий {pt.get("error") or pt.get("crash")}')
            continue
        _, v, t, after = oracle_case(data, ev, c, cache)
        e, ties = compare_rows(c['id'], v, t, after, pt['result'], pa['result'])
        groups[g] += e
        all_ties += [dict(x, group=g) for x in ties]
        counts[g] += len(v['control_points'])
        if c.get('expect'):  # ожидание по построению (real-sources), независимо от оракула
            rows = {r['id']: r for r in pa['result']['rows']}
            for pid, x in c['expect'].items():
                r, b = rows[pid], pt['result']['base'][pid]
                if b != {'id': x['base_id'], 'mm': x['base_mm']} or r['after_mm'] != x['after_mm'] or r['nearest_after']['kind'] != x['after_kind']:
                    groups[g].append(f'{c["id"]}/{pid} (запись {x["record"]}): plan base {b}, after {r["nearest_after"]} {r["after_mm"]} ≠ построению {x}')
    rec('S1-nearest-fixtures', 'FAIL' if groups['r8'] else 'PASS',
        f'table/after/bind/cand-случаи r8 (этапы 1–3) на plan.precompute/evaluatePlan: {counts["r8"]} точек, '
        f'ближайшая запись, мм до кандидатов, after и delta = оракул r8; расхождений {len(groups["r8"])}', mismatches=groups['r8'][:20])
    n_rec = sum(len(c['expect']) for c in scan['cases'] if c['kind'] == 'real_sources')
    rec('S1-real-sources', 'FAIL' if groups['real_sources'] else 'PASS',
        f'точка в координатах каждой из {n_rec} настоящих записей школ/поликлиник обоих городов: до = 0 мм, ближайшая — меньший ID среди '
        f'записей в тех же координатах, кандидат поверх записи не вытесняет source; = построению и оракулу; расхождений {len(groups["real_sources"])}',
        mismatches=groups['real_sources'][:20])
    rec('S1-random', 'FAIL' if groups['random'] else 'PASS',
        f'{sum(1 for c in scan["cases"] if c["kind"] == "random")} seeded synthetic сценариев, {counts["random"]} строк evaluatePlan '
        f'(before/after/delta, мм до 16 кандидатов) = оракул; расхождений {len(groups["random"])}', mismatches=groups['random'][:20])
    real_ties = [x for x in all_ties if x['group'] == 'real_sources']
    distinct = sorted({tuple(x['tied_ids']) for x in all_ties})
    rec('S1-ties', 'PASS' if not any(groups.values()) else 'FAIL',
        f'ничьих в сверке: {len(all_ties)} (на настоящих записях {len(real_ties)}, различных наборов {len(distinct)}); plan.js всегда выбирает меньший ID. '
        'Строка evaluatePlan содержит один nearest_before без числа ничьих: остальные записи в тех же координатах пользователю не видны',
        tie_sets=[list(t) for t in distinct], examples=all_ties[:6])

    # ---- S1-qa: facts.qaOf (видно в интерфейсе) против флагов оракула ----
    errs, gaps = [], []
    for city in ('astana', 'shymkent'):
        qa_ui = {x['id']: x['qa'] for x in res['Q:' + city]['result']}
        for cat in ('school', 'outpatient_clinic'):
            octx = R.build_context(data, ev, city, cat)
            for s in octx['sources']:
                fl = R.source_evidence(octx, s['key'])['flags']
                ui = qa_ui[s['id']]
                ui_col = [q for q in ui if q['code'] == 'COLOCATED']
                o_col = [f for f in fl if f['code'] == 'colocated']
                if bool(ui_col) != bool(o_col) or (o_col and len(ui_col[0]['ids']) != o_col[0]['size']):
                    errs.append(f'{city}/{s["id"]}: COLOCATED UI {ui_col} ≠ оракул {o_col}')
                ui_dup = sorted(i for q in ui if q['code'] == 'POSSIBLE_DUPLICATE' for i in q['ids'] if i != s['id'])
                o_dup = sorted(f['other'].split(':', 1)[1] for f in fl if f['code'] == 'possible_duplicate')
                if ui_dup != o_dup:
                    errs.append(f'{city}/{s["id"]}: POSSIBLE_DUPLICATE UI {ui_dup} ≠ оракул {o_dup}')
                if any(q['code'] == 'CATEGORY_DOUBT' for q in ui) != any(f['code'] == 'category_doubt' for f in fl):
                    errs.append(f'{city}/{s["id"]}: CATEGORY_DOUBT')
                sh = [f for f in fl if f['code'] == 'shared_coordinates']
                if sh and not ui_col:
                    gaps.append({'city': city, 'category': cat, 'id': s['id'], 'name': s['name'], 'same_coordinates_with': sh[0]['count'],
                                 'ui_qa': [q['code'] for q in ui]})
    rec('S1-qa', 'FAIL' if errs else 'PASS',
        f'QA у каждой записи категории (facts.qaOf, как в таблице плана) = флагам оракула r8: COLOCATED/размер, POSSIBLE_DUPLICATE/пары, '
        f'CATEGORY_DOUBT; ошибок {len(errs)}. Записей с общими координатами без метки COLOCATED (порог ≥3): {len(gaps)}',
        errors=errs[:20], shared_without_colocated=gaps)

    # ---- S1-coincident-not-duplicate ----
    errs, facts = [], {}
    for city in ('astana', 'shymkent'):
        places = data['cities'][city]['places']
        pl = {p['id']: p for p in places}
        q = ev['cities'][city]['qa']
        ctx_places = res['C:' + city]['result']['places']
        by_xy_data, by_xy_plan = {}, {}
        for p in places:
            if p['group'] in ('school', 'outpatient_clinic'):
                by_xy_data.setdefault((p['group'], p['lon'], p['lat']), []).append(p['id'])
        for pid, grp, lon, lat in ctx_places:
            by_xy_plan.setdefault((grp, lon, lat), []).append(pid)
        if {k: sorted(v) for k, v in by_xy_data.items()} != {k: sorted(v) for k, v in by_xy_plan.items()}:
            errs.append(f'{city}: plan.js контекст сливает или теряет записи в общих координатах')
        for c in near:
            if c['city'] == city and res['A:' + c['id']]['ok']:
                n = sum(1 for p in places if p['group'] == c['category'])
                if res['A:' + c['id']]['result']['source_candidates'] != n:
                    errs.append(f'{c["id"]}: source_candidates {res["A:" + c["id"]]["result"]["source_candidates"]} ≠ {n} записей категории')
        rules = sorted({d['rule'] for d in q['possible_duplicates']})
        if any('coord' in r or 'colocat' in r for r in rules):
            errs.append(f'{city}: правило POSSIBLE_DUPLICATE по координатам: {rules}')
        dup_pairs = {frozenset((d['a'], d['b'])) for d in q['possible_duplicates']}
        same_xy = {}
        for p in places:
            same_xy.setdefault((p['lon'], p['lat']), []).append(p['id'])
        pairs = [frozenset(x) for ids in same_xy.values() for x in itertools.combinations(ids, 2)]
        unflagged = [sorted(x) for x in pairs if x not in dup_pairs]
        cat_groups = [{'category': g, 'lon': lon, 'lat': lat, 'records': [[i, pl[i]['name'], pl[i]['address']] for i in sorted(ids)]}
                      for (g, lon, lat), ids in sorted(by_xy_data.items()) if len(ids) > 1]
        facts[city] = {'pairs_same_coordinates': len(pairs), 'of_them_possible_duplicate': len(pairs) - len(unflagged),
                       'possible_duplicate_rules': rules, 'possible_duplicate_at_distance_0': sum(1 for d in q['possible_duplicates'] if d['distance_m'] == 0),
                       'same_category_groups': cat_groups}
    texts = [x for city in ('astana', 'shymkent') for r in res['Q:' + city]['result'] for x in r['qa']]
    col_txt = [x['text'] for x in texts if x['code'] == 'COLOCATED']
    dup_txt = [x['text'] for x in texts if x['code'] == 'POSSIBLE_DUPLICATE']
    if any('дубл' in t.lower() for t in col_txt) or not all('не проверено' in t for t in col_txt):
        errs.append('текст COLOCATED называет совпадение дубликатом или не говорит «не проверено»')
    if not all(t.startswith('возможный') for t in dup_txt):
        errs.append('текст POSSIBLE_DUPLICATE утверждает дубликат без «возможный»')
    rec('S1-coincident-not-duplicate', 'FAIL' if errs else 'PASS',
        'совпадение координат ≠ дубликат: plan.js хранит каждую запись в общих координатах отдельно (source_candidates = всем записям), '
        f'POSSIBLE_DUPLICATE строится по адресу/имени ({", ".join(sorted({r for f in facts.values() for r in f["possible_duplicate_rules"]}))}), '
        f'из {sum(f["pairs_same_coordinates"] for f in facts.values())} пар записей в одних координатах помечены возможным дублем '
        f'{sum(f["of_them_possible_duplicate"] for f in facts.values())}; тексты UI: COLOCATED — «точное место не проверено», '
        f'POSSIBLE_DUPLICATE — «возможный»; ошибок {len(errs)}', errors=errs, facts=facts,
        colocated_text_example=col_txt[:1], duplicate_text_example=dup_txt[:1])

    ok = integ['file_unchanged'] and integ['loaded_data_unchanged'] and all(v['ctx'] == v['recomputed'] for v in integ['snapshots'].values())
    rec('S1-integrity', 'PASS' if ok else 'FAIL', 'после всех вызовов plan.js data.js/evidence.js и загруженный объект не изменились, '
        'source_snapshot контекста = пересчёту', integrity=integ)
    return summary_and_save(a.json)


if __name__ == '__main__':
    sys.exit(main())
