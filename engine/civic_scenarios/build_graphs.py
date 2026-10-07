"""Пересобрать подготовленные графы и манифест (инструмент разработки, не сервер).

    python3 -m engine.civic_scenarios.build_graphs           # K03 из git-объекта закреплённого коммита
    python3 -m engine.civic_scenarios.build_graphs --check   # только сверить с файлами в graphs/

Источник читается через `git show <commit>:<path>` (нужен fetch ветки claude/beautiful-clarke-sbzomj).
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from .adapters import k03
from .canon import graph_digest

HERE = Path(__file__).resolve().parent
GRAPHS = HERE / "graphs"


def k03_raw():
    ref = f"{k03.SOURCE['commit']}:{k03.SOURCE['path']}"
    return subprocess.run(["git", "show", ref], cwd=HERE, check=True, capture_output=True).stdout


def dump(obj):
    return (json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    civic = k03.adapt(k03_raw())
    out = GRAPHS / f"{civic['id']}.graph.json"
    data = dump(civic)
    if a.check:
        ok = out.read_bytes() == data
        print(("OK " if ok else "DIFF ") + str(out.relative_to(HERE.parents[1])))
        return 0 if ok else 1
    out.write_bytes(data)
    print(out.relative_to(HERE.parents[1]), civic["digest"], len(data), "bytes")
    syn = json.loads((GRAPHS / "synthetic-tiny-v1.graph.json").read_text("utf-8"))
    assert graph_digest(syn) == syn["digest"]
    manifest = {"graphs": []}
    for g, fname in ((syn, "synthetic-tiny-v1.graph.json"), (civic, out.name)):
        manifest["graphs"].append({
            "id": g["id"], "file": fname, "city": g["city"], "mode": g["mode"], "evidence_type": g["evidence_type"],
            "digest": g["digest"], "file_sha256": hashlib.sha256((GRAPHS / fname).read_bytes()).hexdigest(),
            "nodes": len(g["nodes"]), "edges": len(g["edges"]), "label": g["label"],
            "source": g.get("source"), "license": g.get("license"),
        })
    manifest["not_ready"] = [k03.driving_not_ready()]
    (GRAPHS / "MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
