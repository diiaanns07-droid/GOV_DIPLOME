"""K03 round 4: регрессионный тест исправления k03_assign_v2.

  python3 research/round-4-results/K03/test_regression.py      (или pytest этого файла)
Ничего не записывает. Требует fixtures.json (создаётся review_validator.py).
"""
import json
import math
import subprocess
import unittest

import k03_review_lib as k

REGRESSION = {'AST-HOLE-in0.5', 'AST-HOLE-out0.5', 'AST-VER-D2'}  # D1, D1, D2


def load_fixtures():
    out = []
    for f in json.loads((k.HERE / 'fixtures.json').read_text(encoding='utf-8'))['fixtures']:
        if f.get('lon_is_nan'):
            f = dict(f, lon=math.nan)
        out.append(f)
    return out


class K03AssignV2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v1, cls.v2 = k.load_v1(), k.load_v2()
        cls.L = cls.v1.Layers()
        cls.F = load_fixtures()

    def check(self, m, f):
        r = m.assign(self.L, f['lon'], f['lat'])
        return r['status'] == f['expected_status'] and (
            f['expected_district'] is None or r.get('district') == f['expected_district']), r

    def test_patch_file_matches_spec_and_applies(self):
        self.assertEqual(k.PATCH.read_text(encoding='utf-8'), k.unified_patch())
        rel = k.PATCH.relative_to(k.ROOT)
        subprocess.run(['git', 'apply', '--check', str(rel)], cwd=k.ROOT, check=True)

    def test_reviewed_file_is_snapshot(self):
        blob = subprocess.check_output(['git', 'hash-object', str(k.V1_PATH)], cwd=k.ROOT, text=True).strip()
        self.assertEqual(blob, '23b9fe45b0b447f080ee63bb3a7792ffe7d79497')

    def test_v2_passes_all_fixtures(self):
        bad = [(f['id'], r['status'], r.get('reason')) for f in self.F for ok, r in [self.check(self.v2, f)] if not ok]
        self.assertEqual(bad, [])

    def test_v1_fails_exactly_regression_cases(self):
        failed = {f['id'] for f in self.F if not self.check(self.v1, f)[0]}
        self.assertEqual(failed, REGRESSION)

    def test_v2_never_matches_inside_tolerance_or_zone(self):
        for f in self.F:
            r = self.v2.assign(self.L, f['lon'], f['lat'])
            if f['expected_status'] in ('ambiguous', 'unmatched', 'outside', 'invalid'):
                self.assertNotEqual(r['status'], 'matched', f['id'])
                self.assertIsNone(r.get('district'), f['id'])

    def test_shymkent_unchanged(self):
        for f in self.F:
            if f['city'] == 'shymkent':
                a, b = self.v1.assign(self.L, f['lon'], f['lat']), self.v2.assign(self.L, f['lon'], f['lat'])
                self.assertEqual((a['status'], a.get('district')), (b['status'], b.get('district')), f['id'])

    def test_v2_internal_selftest(self):
        ok, cases = self.v2.selftest(self.L)
        self.assertTrue(ok, [c['case'] for c in cases if not c['passed']])
        self.assertTrue(any('v2 regression' in c['case'] for c in cases))


if __name__ == '__main__':
    unittest.main(verbosity=2)
