"""K03 r9: независимый Python-оракул построителя случаев исключения (resilience_cases.js) и nearest по оставшимся записям.

Те же правила и коды ошибок, что и в JS, но отдельная реализация: каталог строится прямо из data.js/evidence.js (без plan.js),
source_snapshot — независимый пересчёт формулы plan.js, канонический JSON и числа — по правилам JSON.stringify / Number#toString.
Ничего не выбирает автоматически; данные не изменяет (возвращает копии).
"""
import copy
import hashlib
import json
import sys
import unicodedata
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from r9_common import R, plan_snapshot, u16  # noqa: E402

ENVELOPE, VERSION, MANIFEST = 'city-resilience-v1', 'k03-cases-v1', 'k03-exclusion-manifest-v1'
CATEGORIES = ('school', 'outpatient_clinic')
MAX_USER_CASES, MAX_LABEL, MAX_ID = 7, 120, 64
RESERVED_CASE_ID = 'base'
NOTE_RU = 'Условно исключаем из расчёта; это не подтверждение закрытия. Пустые исходные данные не означают отсутствие услуги.'
DERIVED = ('derived_results', 'per_case', 'worst_vector', 'worst_case_ids', 'nominal', 'robust', 'evaluated', 'feasible_count',
           'resilience_problem_digest', 'resilience_scenario_digest', 'price_of_robustness_m', 'verified', 'imported')


class CaseErr(Exception):
    def __init__(self, code, path, detail=''):
        super().__init__(f'{code} @ {path}: {detail}')
        self.code, self.path, self.detail = code, path, detail


# ---------- JSON.stringify / Number#toString ----------
def js_num(x):
    if isinstance(x, bool):
        return 'true' if x else 'false'
    if isinstance(x, int):
        return str(x)
    if x != x or x in (float('inf'), float('-inf')):
        return 'null'
    if x == 0:
        return '0'
    sign, digits, exp = Decimal(repr(abs(x))).as_tuple()
    ds = ''.join(map(str, digits)).rstrip('0') or '0'
    exp += len(digits) - len(ds)
    k, n = len(ds), exp + len(ds)
    neg = '-' if x < 0 else ''
    if k <= n <= 21:
        return neg + ds + '0' * (n - k)
    if 0 < n <= 21:
        return neg + ds[:n] + '.' + ds[n:]
    if -6 < n <= 0:
        return neg + '0.' + '0' * (-n) + ds
    e = n - 1
    return neg + ds[0] + ('.' + ds[1:] if k > 1 else '') + 'e' + ('+' if e > 0 else '-') + str(abs(e))


def js_str(s):
    out = ['"']
    for ch in s:
        o = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == '\\':
            out.append('\\\\')
        elif ch in '\b\f\n\r\t':
            out.append({'\b': '\\b', '\f': '\\f', '\n': '\\n', '\r': '\\r', '\t': '\\t'}[ch])
        elif o < 0x20 or 0xD800 <= o <= 0xDFFF:
            out.append('\\u%04x' % o)
        else:
            out.append(ch)
    return ''.join(out) + '"'


def stringify(v, sort_keys=False):
    if v is None:
        return 'null'
    if isinstance(v, (bool, int, float)):
        return js_num(v)
    if isinstance(v, str):
        return js_str(v)
    if isinstance(v, (list, tuple)):
        return '[' + ','.join(stringify(x, sort_keys) for x in v) + ']'
    keys = sorted(v, key=u16) if sort_keys else list(v)
    return '{' + ','.join(js_str(k) + ':' + stringify(v[k], sort_keys) for k in keys) + '}'


def sha(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def decimals(x):
    s = js_num(abs(x))
    return None if 'e' in s else (len(s) - s.index('.') - 1 if '.' in s else 0)


# ---------- ID и подпись ----------
def is_id(v):
    return (isinstance(v, str) and 1 <= len(v) <= MAX_ID and unicodedata.normalize('NFC', v) == v
            and all(unicodedata.category(ch)[0] in 'LN' or ch in '_.-' for ch in v))


def bad_label_char(ch):
    return unicodedata.category(ch) in ('Cc', 'Cs')


# ---------- каталог ----------
def source_catalog(data, evidence, city, category):
    if category not in CATEGORIES:
        raise CaseErr('bad_category', 'category', str(category)[:40])
    c = (data.get('cities') or {}).get(city)
    if not c:
        raise CaseErr('bad_city', 'city', str(city)[:40])
    e = ((evidence or {}).get('cities') or {}).get(city) or {}
    qa = e.get('qa')
    by_xy = {}
    for p in c['places']:
        by_xy.setdefault((p['lon'], p['lat']), []).append(p)
    recs = []
    for p in sorted((p for p in c['places'] if p['group'] == category), key=lambda p: u16(p['id'])):
        others = [o for o in by_xy[(p['lon'], p['lat'])] if o['id'] != p['id']]
        col = next((g for g in qa['colocated'] if p['id'] in g['ids']), None) if qa else None
        dups = []
        if qa:
            for d in qa['possible_duplicates']:
                if p['id'] in (d['a'], d['b']):
                    dups.append({'other': d['b'] if d['a'] == p['id'] else d['a'], 'rule': d['rule'], 'distance_m': d['distance_m']})
        cd = (qa or {}).get('category_doubt', {}).get(p['id']) if qa else None
        recs.append({
            'id': p['id'], 'category': p['group'], 'name': p.get('name'), 'address': p.get('address'), 'lon': p['lon'], 'lat': p['lat'],
            'coord_decimals': {'lon': decimals(p['lon']), 'lat': decimals(p['lat'])},
            'provenance': {'overture_category': p.get('category'), 'overture_version': p.get('overture_version'),
                           'confidence': p.get('confidence'), 'operating_status': p.get('operating_status'),
                           'sources': [{'dataset': s.get('dataset'), 'record_id': s.get('record_id'), 'license': s.get('license'),
                                        'update_time': s.get('update_time')} for s in p.get('sources') or []]},
            'record_sha256': sha(stringify(p, sort_keys=True)),
            'position_status': 'source_reported_unverified',
            'qa': {'available': bool(qa),
                   'colocated': {'lon': col['lon'], 'lat': col['lat'], 'size': len(col['ids']), 'ids': sorted(col['ids'], key=u16)} if col else None,
                   'possible_duplicates': sorted(dups, key=lambda d: u16(d['other'])),
                   'category_doubt': {'rule': cd['rule'], 'reason': cd['reason']} if cd else None},
            'same_coordinates': {'in_category': sorted((o['id'] for o in others if o['group'] == category), key=u16),
                                 'other_categories': sorted((o['id'] for o in others if o['group'] != category), key=u16)}})
    return {'version': VERSION, 'city_id': city, 'category': category, 'source_snapshot': plan_snapshot(data, city),
            'release': c.get('release'), 'qa_available': bool(qa), 'records': copy.deepcopy(recs)}


def source_index(data):
    idx = {}
    for city, c in data['cities'].items():
        for p in c['places']:
            idx.setdefault(p['id'], []).append((city, p['group']))
    return idx


# ---------- проверки ----------
def _classify(cat, index, cand, x, path):
    if not is_id(x):
        raise CaseErr('bad_source_id', path)
    if any(r['id'] == x for r in cat['records']):
        return
    where = (index or {}).get(x)
    if where and any(c == cat['city_id'] for c, _ in where):
        raise CaseErr('other_category_source', path)
    if where:
        raise CaseErr('other_city_source', path)
    if cand and x in cand:
        raise CaseErr('candidate_not_source', path)
    raise CaseErr('unknown_source_id', path)


def _exclusions(cat, ids, path, index, cand):
    if not isinstance(ids, list):
        raise CaseErr('bad_shape', path)
    if not ids:
        raise CaseErr('empty_exclusion', path)
    if len(ids) > len(cat['records']):
        raise CaseErr('too_many_exclusions', path)
    seen = set()
    for k, x in enumerate(ids):
        _classify(cat, index, cand, x, f'{path}[{k}]')
        if x in seen:
            raise CaseErr('duplicate_source_id', f'{path}[{k}]')
        seen.add(x)
    return sorted(ids, key=u16)


def _label(v, path):
    if not isinstance(v, str) or not v:
        raise CaseErr('bad_label', path)
    if len(v) > MAX_LABEL:
        raise CaseErr('bad_label', path)
    if any(bad_label_char(ch) for ch in v):
        raise CaseErr('bad_label', path)
    return v


def _case_id(v, path):
    if not is_id(v):
        raise CaseErr('bad_case_id', path)
    if v == RESERVED_CASE_ID:
        raise CaseErr('reserved_case_id', path)
    return v


def validate_cases(cat, cases, index=None, candidate_ids=None):
    cand = set(candidate_ids) if candidate_ids else None
    if not isinstance(cases, list):
        raise CaseErr('bad_shape', 'cases')
    if not cases:
        raise CaseErr('no_cases', 'cases')
    if len(cases) > MAX_USER_CASES:
        raise CaseErr('too_many_cases', 'cases')
    ids, clean = set(), []
    for i, c in enumerate(cases):
        p = f'cases[{i}]'
        if not isinstance(c, dict):
            raise CaseErr('bad_shape', p)
        for k in c:
            if k not in ('id', 'label', 'disabled_source_ids'):
                raise CaseErr('unknown_field', f'{p}.{k}'[:80])
        for k in ('id', 'label', 'disabled_source_ids'):
            if k not in c:
                raise CaseErr('missing_field', f'{p}.{k}')
        _case_id(c['id'], f'{p}.id')
        if c['id'] in ids:
            raise CaseErr('duplicate_case_id', f'{p}.id')
        ids.add(c['id'])
        _label(c['label'], f'{p}.label')
        clean.append({'id': c['id'], 'label': c['label'],
                      'disabled_source_ids': _exclusions(cat, c['disabled_source_ids'], f'{p}.disabled_source_ids', index, cand)})
    by = {}
    for c in clean:
        by.setdefault(tuple(c['disabled_source_ids']), []).append(c['id'])
    same = sorted((sorted(g, key=u16) for g in by.values() if len(g) > 1), key=lambda g: u16(g[0]))
    return {'cases': clean, 'with_base': [{'id': RESERVED_CASE_ID, 'label': 'Исходные данные', 'disabled_source_ids': []}] + clean,
            'identical_sets': same}


# ---------- построители ----------
def _clip(s, n):
    cps = ''.join(' ' if bad_label_char(ch) else ch for ch in str(s))
    return cps if len(cps) <= n else cps[:n - 1] + '…'


def default_label(kind, recs, extra=None):
    nm = [r['name'] or 'без названия' for r in recs]
    if kind == 'single':
        return _clip(f'Условно без записи: {nm[0]}', MAX_LABEL)
    if kind == 'group':
        return _clip(f'Условно без выбранных записей ({len(recs)}): {", ".join(nm)}', MAX_LABEL)
    return _clip(f'Условно без записей QA-группы COLOCATED ({js_num(extra["lon"])}, {js_num(extra["lat"])}): {len(recs)} из {extra["size"]}',
                 MAX_LABEL)


def _make(cat, ids, kind, opts, extra=None):
    opts = opts or {}
    cid = _case_id(opts.get('id'), 'id')
    srt = _exclusions(cat, ids, 'disabled_source_ids', opts.get('index'), set(opts['candidate_ids']) if opts.get('candidate_ids') else None)
    recs = [next(r for r in cat['records'] if r['id'] == x) for x in srt]
    label = _label(opts['label'] if 'label' in opts else default_label(kind, recs, extra), 'label')
    return {'id': cid, 'label': label, 'disabled_source_ids': srt}


def single_case(cat, source_id, opts=None):
    return _make(cat, [source_id], 'single', opts)


def group_case(cat, source_ids, opts=None):
    return _make(cat, source_ids, 'group', opts)


def colocated_groups(evidence, cat):
    e = ((evidence or {}).get('cities') or {}).get(cat['city_id']) or {}
    if not e.get('qa'):
        return {'qa_available': False, 'groups': []}
    mine = {r['id'] for r in cat['records']}
    return {'qa_available': True, 'groups': [
        {'index': i, 'lon': g['lon'], 'lat': g['lat'], 'size': len(g['ids']),
         'ids_in_category': sorted((x for x in g['ids'] if x in mine), key=u16),
         'ids_other_categories': sorted((x for x in g['ids'] if x not in mine), key=u16)} for i, g in enumerate(e['qa']['colocated'])]}


def colocated_case(evidence, cat, index, opts=None):
    g = colocated_groups(evidence, cat)
    if not g['qa_available']:
        return {'status': 'qa_unavailable', 'case': None, 'group': None, 'reason': 'в срезе нет QA-меток; группа не создаётся'}
    if not g['groups']:
        return {'status': 'no_qa_group', 'case': None, 'group': None, 'reason': 'в срезе нет групп COLOCATED; группа не создаётся'}
    if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(g['groups']):
        raise CaseErr('unknown_qa_group', 'group')
    grp = g['groups'][index]
    if not grp['ids_in_category']:
        return {'status': 'no_records_in_category', 'case': None, 'group': grp, 'reason': 'в группе нет записей этой категории'}
    return {'status': 'ok', 'case': _make(cat, grp['ids_in_category'], 'colocated', opts, grp), 'group': grp}


def check_envelope_shape(obj):
    if not isinstance(obj, dict):
        raise CaseErr('bad_shape', '$')
    for k in obj:
        if k not in ('schema_version', 'plan', 'cases'):
            raise CaseErr('derived_not_accepted' if k in DERIVED else 'unknown_field', k[:60])
    for k in ('schema_version', 'plan', 'cases'):
        if k not in obj:
            raise CaseErr('missing_field', k)
    if obj['schema_version'] != ENVELOPE:
        raise CaseErr('bad_version', 'schema_version')
    if not isinstance(obj['plan'], dict):
        raise CaseErr('bad_shape', 'plan')
    if 'derived_results' in obj['plan']:
        raise CaseErr('derived_not_accepted', 'plan.derived_results')
    return obj


def exclusion_digest(cat, cases):
    rows = sorted(([c['id'], c['label'], sorted(c['disabled_source_ids'], key=u16)] for c in cases), key=lambda r: u16(r[0]))
    return 'sha256:' + sha(stringify([VERSION, cat['city_id'], cat['category'], cat['source_snapshot'], rows]))


def exclusion_manifest(cat, validated, build=None):
    used = sorted({x for c in validated['cases'] for x in c['disabled_source_ids']}, key=u16)
    same = {i: [x for x in g if x != i] for g in validated['identical_sets'] for i in g}
    return copy.deepcopy({'schema': MANIFEST, 'note': NOTE_RU, 'city_id': cat['city_id'], 'category': cat['category'],
                          'base_source_snapshot': cat['source_snapshot'], 'release': cat['release'], 'qa_available': cat['qa_available'],
                          'build': build, 'exclusion_digest': exclusion_digest(cat, validated['cases']),
                          'cases': [{'id': c['id'], 'label': c['label'], 'disabled_source_ids': c['disabled_source_ids'],
                                     'identical_to': same.get(c['id'], [])} for c in validated['cases']],
                          'records': {x: next(r for r in cat['records'] if r['id'] == x) for x in used}})


# ---------- этап 3: nearest по оставшимся записям случая (с нуля, гаверсинус haversine-mm-v1) ----------
def case_baseline(data, city, category, disabled, control_points):
    """Для каждой точки: {'id', 'mm', 'tied_ids'} ближайшей НЕисключённой записи категории или None (записей не осталось)."""
    off = set(disabled)
    srcs = [p for p in data['cities'][city]['places'] if p['group'] == category and p['id'] not in off]
    out = []
    for cp in control_points:
        opts = [(R.mm_between(cp, s), s['id']) for s in srcs]
        if not opts:
            out.append(None)
            continue
        mm = min(o[0] for o in opts)
        tied = sorted((i for d, i in opts if d == mm), key=u16)
        out.append({'id': tied[0], 'mm': mm, 'tied_ids': tied})
    return out
