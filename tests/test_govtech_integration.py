"""The integrated planner must keep its pinned data/math and document UI adaptations."""
import hashlib
import json
from pathlib import Path


def test_integrated_govtech_assets_match_provenance():
    root = Path(__file__).resolve().parents[1] / "web" / "govtech"
    manifest = json.loads((root / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
    adapted = set(manifest["adaptations"])
    assert adapted == {"plan-ui.js", "resilience-ui.js"}
    for item in manifest["files"]:
        digest = hashlib.sha256((root / "core" / item["file"]).read_bytes()).hexdigest()
        assert digest == item["integrated_sha256"], item["file"]
        if item["file"] not in adapted:
            assert digest == item["sha256"], "Undocumented change to pinned core: " + item["file"]


def test_school_case_assets_are_served_and_linked():
    """The school-access main path is part of the one page on 8501, served by explicit whitelist only."""
    from ui.web_server import ASSETS

    web = Path(__file__).resolve().parents[1] / "web"
    page = (web / "index.html").read_text(encoding="utf-8")
    for name in ("school/case.js", "school/note.js", "school/school-ui.js", "school/school.css"):
        assert "/govtech/" + name in ASSETS
        assert (web / "govtech" / name).is_file()
        assert "/govtech/" + name in page
    # school-ui.js needs the shell and the pinned core loaded before it
    assert page.index("/govtech/shell.js") < page.index("/govtech/school/case.js") < page.index("/govtech/school/school-ui.js")
    assert page.count("<canvas") == 0 and "<iframe" not in page


def test_school_case_packages_match_manifest():
    """Prepared case packages are served byte-identical to the colleague's file recorded in SCHOOL_MANIFEST.json."""
    root = Path(__file__).resolve().parents[1] / "web" / "govtech" / "school"
    manifest = json.loads((root / "SCHOOL_MANIFEST.json").read_text(encoding="utf-8"))
    from ui.web_server import ASSETS

    assert manifest["cases"]
    for item in manifest["cases"]:
        assert hashlib.sha256((root / item["file"]).read_bytes()).hexdigest() == item["sha256"], item["file"]
        assert "/govtech/school/" + item["file"] in ASSETS
        assert len(item["source_commit"]) == 40
