"""K10 round 8: tests of k10plan.cli (stdlib unittest).

    python3 -m unittest discover -s tests -p "test_*.py" -v                      # pack-only tests
    K10_APP_ROOT=<BUILD prototypes/city-evidence> python3 -m unittest ...         # + tests against a BUILD app root
"""
import contextlib
import copy
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from k10plan import cli  # noqa: E402
from k10plan import oracle as O  # noqa: E402
from k10plan import slice as S  # noqa: E402

PACKS = ROOT / "packs"
APP = os.environ.get("K10_APP_ROOT")


def run_cli(*argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = cli.main(list(argv))
    return code, buf.getvalue()


def tree(d):
    return {str(p.relative_to(d)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(d).rglob("*")) if p.is_file()}


def pack_files():
    return sorted(p for p in PACKS.glob("*.json") if p.name != "INDEX.json")


class PackOnly(unittest.TestCase):
    def test_preview_every_pack_recomputes_equal(self):
        before = tree(PACKS)
        for p in pack_files():
            code, out = run_cli("preview", str(p))
            self.assertEqual(code, 0, p.name)
            if "invalid" not in p.name:
                self.assertIn("Пересчёт оракулом = ожидаемое в пакете: да", out, p.name)
                self.assertIn("Ограничения:", out)
        self.assertEqual(tree(PACKS), before)  # previews never write into the packs

    def test_json_matches_stored(self):
        p = json.loads((PACKS / "astana-school-base.json").read_text(encoding="utf-8"))
        code, out = run_cli("preview", str(PACKS / "astana-school-base.json"), "--format", "json")
        v = json.loads(out)
        self.assertEqual((code, v["matches_stored_expected"]), (0, True))
        self.assertEqual(v["result"], p["expected"])

    def test_identical_plans_named_once(self):
        _, out = run_cli("preview", str(PACKS / "shymkent-school-base.json"))
        self.assertIn("это одно решение, а не три", out)
        self.assertIn("= среднее (mean)", out)

    def test_infeasible_explained(self):
        _, out = run_cli("preview", str(PACKS / "shymkent-school-conflict-budget.json"))
        self.assertIn("Допустимых наборов нет", out)
        self.assertIn("обязательные кандидаты стоят больше бюджета", out)

    def test_tampered_pack_detected(self):
        p = json.loads((PACKS / "synthetic-ties.json").read_text(encoding="utf-8"))
        p["expected"]["optimize"]["objectives"]["mean"]["selected_ids"] = ["t2"]
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "x.json"
            f.write_text(json.dumps(p), encoding="utf-8")
            code, out = run_cli("preview", str(f))
        self.assertEqual(code, 1)
        self.assertIn("НЕТ", out)

    def test_html_escapes_ids_and_names(self):
        p = json.loads((PACKS / "synthetic-ties.json").read_text(encoding="utf-8"))
        evil = '<img src=x onerror="alert(1)">'
        p["scenario"]["candidates"][0]["id"] = evil
        p["synthetic_slice"]["records"][0]["name"] = "<script>alert(2)</script>"
        p.pop("expected")
        with tempfile.TemporaryDirectory() as d:
            f, o = Path(d) / "x.json", Path(d) / "x.html"
            f.write_text(json.dumps(p), encoding="utf-8")
            code, _ = run_cli("preview", str(f), "--format", "html", "--out", str(o), "--plan", "manual")
            h = o.read_text(encoding="utf-8")
        self.assertEqual(code, 0)
        self.assertNotIn("<img", h)
        self.assertNotIn("<script>", h)
        self.assertIn("&lt;img src=x onerror=&quot;alert(1)&quot;&gt;", h)

    def test_export_too_large_exact_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            o = Path(d) / "big.json"
            with contextlib.redirect_stdout(io.StringIO()):
                code = cli.main(["export-case", str(PACKS / "shymkent-school-invalid-inputs.json"), "too_large", "--out", str(o)])
            raw = o.read_bytes()
        self.assertEqual((code, len(raw)), (0, 262145))
        with self.assertRaises(O.PlanError) as e:
            O.parse_strict(raw)
        self.assertEqual(e.exception.code, "too_large")


@unittest.skipUnless(APP, "set K10_APP_ROOT to an extracted BUILD prototypes/city-evidence")
class WithAppRoot(unittest.TestCase):
    def test_scenario_files_and_invalid_files(self):
        before = S.input_manifest(APP)
        for f in sorted((PACKS / "scenarios").glob("*.json")):
            code, out = run_cli("run", str(f), "--app-root", APP, "--format", "json")
            if f.name.startswith("synthetic-"):  # synthetic geometry is not a city of the app root: refused before computing
                self.assertEqual((code, json.loads(out)["code"]), (2, "bad_city"), f.name)
                continue
            self.assertEqual(code, 0, f.name)
            p = json.loads((PACKS / f.name).read_text(encoding="utf-8"))
            self.assertEqual(json.loads(out)["result"]["optimize"], p["expected"]["optimize"], f.name)
        for pk in ("shymkent-school-invalid-inputs", "astana-school-invalid-inputs"):
            pack = json.loads((PACKS / f"{pk}.json").read_text(encoding="utf-8"))
            for c in pack["invalid_cases"]:
                f = PACKS / "scenarios" / "invalid" / pk / f"{c['case_id']}.json"
                if not f.exists():
                    continue  # too_large: exported on demand
                code, out = run_cli("run", str(f), "--app-root", APP, "--city", pack["city_id"], "--format", "json")
                if c["expected"]["rejected"]:
                    self.assertEqual((code, json.loads(out)["code"]), (2, c["expected"]["code"]), c["case_id"])
                else:
                    self.assertEqual(code, 0, c["case_id"])
        self.assertEqual(S.input_manifest(APP), before)  # the BUILD inputs are only read

    def test_preview_against_app_root_and_verify(self):
        code, out = run_cli("preview", str(PACKS / "shymkent-outpatient_clinic-qa-nearest.json"), "--app-root", APP, "--plan", "baseline")
        self.assertEqual(code, 0)
        self.assertIn("app-root совпадает с копией пакета", out)
        self.assertIn("COLOCATED", out)
        code, out = run_cli("verify-inputs", "--app-root", APP, "--index", str(PACKS / "INDEX.json"))
        self.assertEqual(code, 0, out)

    def test_stale_pack_reported(self):
        p = json.loads((PACKS / "astana-school-base.json").read_text(encoding="utf-8"))
        p2 = copy.deepcopy(p)
        p2["source_copy"]["category_records"][0]["lon"] += 0.001
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "x.json"
            f.write_text(json.dumps(p2), encoding="utf-8")
            code, out = run_cli("preview", str(f), "--app-root", APP)
        self.assertEqual(code, 1)
        self.assertIn("ОТЛИЧАЕТСЯ", out)


if __name__ == "__main__":
    unittest.main()
