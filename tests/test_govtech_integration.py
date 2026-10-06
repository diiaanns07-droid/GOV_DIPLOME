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
