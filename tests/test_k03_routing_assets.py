"""K03 r10: модуль pedestrian-v1 и графы в web/govtech/k03 совпадают с K03_MANIFEST.json (без незадокументированных правок)."""
import hashlib
import json
from pathlib import Path


def test_k03_routing_assets_match_manifest():
    root = Path(__file__).resolve().parents[1] / "web" / "govtech" / "k03"
    manifest = json.loads((root / "K03_MANIFEST.json").read_text(encoding="utf-8"))
    names = {item["file"] for item in manifest["files"]}
    assert names == {"routing.js", "school-access-routing.js", "shymkent.graph.json", "astana.graph.json"}
    for item in manifest["files"]:
        assert hashlib.sha256((root / item["file"]).read_bytes()).hexdigest() == item["sha256"], item["file"]
    for city, meta in manifest["graphs"].items():
        graph = json.loads((root / f"{city}.graph.json").read_text(encoding="utf-8"))
        assert graph["graph_sha256"] == meta["graph_sha256"] and graph["license"]["id"] == "ODbL-1.0"
