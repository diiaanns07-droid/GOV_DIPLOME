"""Mutation tests for audit_numbers.py: the audit must FAIL on injected label/number defects and not FAIL on
the unmodified BUILD. The BUILD under test is given by --app-root (or env K06_APP_ROOT):

  python3 test_audit_numbers.py --app-root <extracted prototypes/city-evidence> [-v]

Each mutation works on a temporary copy of web/ (+ inputs/), never on the given directory.
"""
import functools, http.server, json, os, re, shutil, sys, tempfile, threading, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_numbers as A

APP_ROOT = os.environ.get("K06_APP_ROOT")


def status(checks, cid):
    return {c["city"]: c["status"] for c in checks if c["id"] == cid}


class Mutations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not APP_ROOT or not os.path.isdir(os.path.join(APP_ROOT, "web")):
            raise unittest.SkipTest("give --app-root <prototypes/city-evidence copy>")

    def mutate(self, fname, fn):
        tmp = tempfile.mkdtemp(prefix="k06r5_")
        self.addCleanup(shutil.rmtree, tmp)
        shutil.copytree(os.path.join(APP_ROOT, "web"), os.path.join(tmp, "web"))
        if os.path.isdir(os.path.join(APP_ROOT, "inputs")):
            os.symlink(os.path.join(os.path.abspath(APP_ROOT), "inputs"), os.path.join(tmp, "inputs"))
        p = os.path.join(tmp, "web", fname)
        txt = open(p, encoding="utf-8").read()
        new = fn(txt)
        self.assertNotEqual(new, txt, "mutation did not apply: " + fname)
        open(p, "w", encoding="utf-8").write(new)
        return A.audit(A.Src(app_root=tmp))

    def data_mut(self, fn):
        def f(txt):
            d = A.js_object(txt, "CITY_EVIDENCE"); fn(d)
            return "window.CITY_EVIDENCE = " + json.dumps(d, ensure_ascii=False) + ";\n"
        return self.mutate("data.js", f)

    def test_0_baseline_has_no_fail(self):
        checks = A.audit(A.Src(app_root=APP_ROOT))
        self.assertFalse([c for c in checks if c["status"] == "FAIL"])

    def test_1_city_total_claim_in_count_label(self):
        ch = self.mutate("app.js", lambda t: t.replace("в срезе", "школ в городе").replace(
            "в полном ответе запроса по квадрату", "школ в городе"))
        self.assertEqual(set(status(ch, "N2_count_labels").values()), {"FAIL"})

    def test_2_unknown_capacity_becomes_zero(self):
        def f(t):
            return re.sub(r'("indicator_id":"capacity\.school_places".*?"value":)null', r"\g<1>0", t, count=2)
        ch = self.mutate("evidence.js", f)
        self.assertIn("FAIL", status(ch, "N3_unknown_not_zero").values())

    def test_3_road_km_shown_without_full_geometry_label(self):
        def f(d):
            for c in d["cities"].values():
                c["counts"]["road_km"] = c["counts"].pop("road_km_full_geometry")
        tmp_checks = None
        # rename the field in data.js and display it in app.js
        tmp = tempfile.mkdtemp(prefix="k06r5_"); self.addCleanup(shutil.rmtree, tmp)
        shutil.copytree(os.path.join(APP_ROOT, "web"), os.path.join(tmp, "web"))
        dp, ap = os.path.join(tmp, "web", "data.js"), os.path.join(tmp, "web", "app.js")
        d = A.js_object(open(dp, encoding="utf-8").read(), "CITY_EVIDENCE"); f(d)
        open(dp, "w", encoding="utf-8").write("window.CITY_EVIDENCE = " + json.dumps(d, ensure_ascii=False) + ";\n")
        t = open(ap, encoding="utf-8").read()
        t2 = t.replace('["Записей объектов"', '["Дорог в квадрате", `${k.road_km} км`, null],\n      ["Записей объектов"', 1)
        self.assertNotEqual(t, t2); open(ap, "w", encoding="utf-8").write(t2)
        tmp_checks = A.audit(A.Src(app_root=tmp))
        self.assertEqual(set(status(tmp_checks, "N5_road_km_full_vs_inside").values()), {"FAIL"})

    def test_3b_full_km_shown_as_inside_square(self):
        ch = self.mutate("app.js", lambda t: t.replace('["Записей объектов"', '["Дорог в квадрате", `${k.road_km_full_geometry} км`, null],\n      ["Записей объектов"', 1))
        self.assertEqual(set(status(ch, "N5_road_km_full_vs_inside").values()), {"FAIL"})

    def test_3c_full_km_shown_with_honest_label(self):
        ch = self.mutate("app.js", lambda t: t.replace('["Записей объектов"', '["Дороги, вся геометрия (в т.ч. за краем)", `${k.road_km_full_geometry} км`, null],\n      ["Записей объектов"', 1))
        self.assertEqual(set(status(ch, "N5_road_km_full_vs_inside").values()), {"PASS"})

    def test_4_length_in_km_not_m(self):
        ch = self.data_mut(lambda d: [s.__setitem__("length_m", round(s["length_m"] / 1000, 4))
                                      for c in d["cities"].values() for s in c["segments"]])
        self.assertEqual(set(status(ch, "N6_segment_length_label").values()), {"FAIL"})

    def test_5_edge_marker_removed(self):
        ch = self.mutate("app.js", lambda t: t.replace(" (вся линия, выходит за квадрат)", ""))
        self.assertEqual(set(status(ch, "N6_segment_length_label").values()), {"FAIL"})

    def test_6_walking_minutes_appear(self):
        ch = self.mutate("app.js", lambda t: t.replace('["По прямой", "num"]', '["По прямой", "num"], [`${Math.round(r.d / 80)} мин пешком`, null]', 1))
        self.assertEqual(set(status(ch, "N7_straight_line_distance").values()), {"FAIL"})

    def test_7_crossing_flag_wrong(self):
        def f(d):
            for c in d["cities"].values():
                s = next(s for s in c["segments"] if s["crosses_edge"]); s["crosses_edge"] = False
        ch = self.data_mut(f)
        self.assertEqual(set(status(ch, "N4_segments_edge").values()), {"FAIL"})

    def test_8_url_mode(self):
        web = os.path.join(APP_ROOT, "web")
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=web)
        h.log_message = lambda *a, **k: None
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        checks = A.audit(A.Src(url=f"http://127.0.0.1:{srv.server_address[1]}/"))
        self.assertFalse([c for c in checks if c["status"] == "FAIL"])
        self.assertEqual(set(status(checks, "N8_provenance_k10").values()), {"SKIP"})


if __name__ == "__main__":
    if "--app-root" in sys.argv:
        i = sys.argv.index("--app-root"); APP_ROOT = sys.argv[i + 1]; del sys.argv[i:i + 2]
    unittest.main()
