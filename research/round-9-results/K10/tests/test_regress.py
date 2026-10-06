"""K10 round 9: does regress.py notice changed packs, source files and source records? (stdlib unittest)

    python3 -m unittest discover -s research/round-9-results/K10/tests -p "test_regress.py" -v
Needs the BUILD commit d865dd4 in the local git (it is extracted byte-exact into a temporary directory).
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import regress as R  # noqa: E402

SHA = "d865dd4a124291e10dd0b7bb1d9eada20d34c268"


def edit_data_js(app, fn):
    p = app / "web/data.js"
    t = p.read_text(encoding="utf-8")
    i, j = t.index("{"), t.rstrip().rindex(";")
    d = json.loads(t[i:j])
    fn(d)
    p.write_text(t[:i] + json.dumps(d, ensure_ascii=False) + t[j:], encoding="utf-8")


class Regress(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="k10r9t_"))
        cls.base = cls.tmp / "base"
        cls.entries = R.extract(SHA, cls.base)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def copy(self):
        d = Path(tempfile.mkdtemp(dir=self.tmp))
        shutil.copytree(self.base / R.PREFIX, d / "app")
        return d / "app"

    def test_extract_is_byte_exact(self):
        self.assertGreater(len(self.entries), 100)
        for e in self.entries[:30]:
            self.assertEqual(R.sha256((self.base / e["path"]).read_bytes()), e["sha256"])

    def test_pristine_sources_pass(self):
        h, i = R.check_sources(self.base / R.PREFIX)
        self.assertEqual((h["status"], i["status"]), ("PASS", "PASS"))
        self.assertEqual((i["cities"]["shymkent"]["school"], i["cities"]["astana"]["outpatient_clinic"]), (15, 16))

    def test_changed_geojson_byte_fails(self):
        app = self.copy()
        p = app / "inputs/k10/data/astana/places_social.geojson"
        p.write_bytes(p.read_bytes() + b" ")
        self.assertEqual(R.check_sources(app)[0]["status"], "FAIL")

    def test_moved_removed_regrouped_records_fail(self):
        for fn, key in ((lambda d: d["cities"]["shymkent"]["places"][0].update(lon=d["cities"]["shymkent"]["places"][0]["lon"] + 1e-5), "changed"),
                        (lambda d: d["cities"]["astana"]["places"].pop(3), "missing"),
                        (lambda d: d["cities"]["shymkent"]["places"][1].update(group="pharmacy"
                                                                               if d["cities"]["shymkent"]["places"][1]["group"] != "pharmacy" else "school"), "changed")):
            app = self.copy()
            edit_data_js(app, fn)
            _, ids = R.check_sources(app)
            self.assertEqual(ids["status"], "FAIL")
            self.assertTrue(any(c[key] for c in ids["cities"].values()), key)

    def test_edited_r8_pack_fails(self):
        d = Path(tempfile.mkdtemp(dir=self.tmp))
        shutil.copytree(R.R8 / "packs", d / "packs")
        p = d / "packs/astana-school-base.json"
        p.write_bytes(p.read_bytes().replace(b'"budget": 700', b'"budget": 701', 1))
        old = R.R8
        try:
            R.R8 = d
            res = R.check_frozen_packs()
        finally:
            R.R8 = old
        self.assertEqual(res["status"], "FAIL")
        self.assertIn("astana-school-base.json", res["differences"])
        self.assertEqual(R.check_frozen_packs()["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
