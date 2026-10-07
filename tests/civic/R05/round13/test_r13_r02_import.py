"""Пакет черновиков R05 раунда 13 через настоящий импортер R02 во временную базу.

По умолчанию — ui/civic_store из этого дерева. R05_R02_ROOT=<изолированная сборка> проверяет закреплённую
поставку R02 (см. research/round-13-results/R05/RUN.txt). Модуль R02 не меняется.
"""

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from r13_helpers import REPO, attach_a, review, review_form_for, run

R02_ROOT = Path(os.environ.get("R05_R02_ROOT") or REPO)
pytestmark = pytest.mark.skipif(not (R02_ROOT / "ui/civic_store/importer.py").exists(),
                                reason=f"NOT_RUN: нет ui/civic_store в {R02_ROOT}")


def civic(db, *argv):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "CIVIC_"))}
    proc = subprocess.run([sys.executable, "-s", "-B", "-m", "ui.civic_store", "--db", str(db), *map(str, argv)],
                          cwd=R02_ROOT, env=env, capture_output=True, text=True, timeout=120)
    try:
        return proc.returncode, json.loads(proc.stdout)
    except ValueError:
        return proc.returncode, proc.stdout + proc.stderr


@pytest.fixture
def built(tool, home):
    assert attach_a(tool, home)[0] == 0
    assert review(tool, home, review_form_for(tool, "test-almaty-closure"))[0] == 0
    assert run(tool, "build")[0] == 0
    return home["root"] / "package.civic-v1.json"


def test_dry_run_import_reimport_keep_stable_ids_and_drafts(built, tmp_path):
    db = tmp_path / "civic.sqlite3"
    assert civic(db, "init")[0] == 0
    code, report = civic(db, "import", built, "--dry-run")
    assert code == 0, report
    assert report["status"] == "dry_run" and report["counts"].get("create") == 1
    assert report["source"] == "r05-astana-r13-verified"
    [entry] = report["items"]
    assert entry["object_id"] == entry["external_id"] == "ast-r05-roadworks-test-almaty-closure"
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM civic_objects").fetchone()[0] == 0   # dry-run ничего не пишет
    code, report = civic(db, "import", built)
    assert code == 0 and report["status"] == "applied" and report["counts"].get("create") == 1
    code, report = civic(db, "import", built)
    assert code == 0 and report["counts"].get("skip_unchanged") == 1 and "create" not in report["counts"]
    with sqlite3.connect(db) as conn:
        rows = conn.execute("SELECT id, publication, import_source FROM civic_objects").fetchall()
    assert rows == [("ast-r05-roadworks-test-almaty-closure", "draft", "r05-astana-r13-verified")]


def test_empty_real_package_imports_nothing(tmp_path):
    db = tmp_path / "civic.sqlite3"
    assert civic(db, "init")[0] == 0
    for name in ("package.civic-v1.json", "historical.civic-v1.json"):
        code, report = civic(db, "import", REPO / "data/civic/astana/round13-verified" / name, "--dry-run")
        assert code == 0, report
        assert report["items"] == [] and report["counts"].get("create", 0) == 0
