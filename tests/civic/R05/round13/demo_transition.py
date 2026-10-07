"""Воспроизводимая демонстрация пути candidate -> evidence attached -> review -> draft package -> импорт R02.

    python3 -s -B tests/civic/R05/round13/demo_transition.py [--r02-root DIR] > transcript.txt

Всё во временном каталоге; данные СИНТЕТИЧЕСКИЕ (example.invalid), реальный пакет R05 не меняется.
Показывает и отказы: сниппет вместо страницы, тот же человек в роли проверяющего, правка после проверки.
"""

import argparse
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import r13_helpers as h  # noqa: E402


def load_tool():
    spec = importlib.util.spec_from_file_location("r05_r13_demo", h.TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def show(title, code, out):
    print(f"\n### {title}\nexit={code}")
    text = json.dumps(out, ensure_ascii=False, indent=1) if not isinstance(out, str) else out
    print(text if len(text) < 2500 else text[:2500] + "\n…")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--r02-root", default=str(h.REPO))
    args = ap.parse_args()
    tool = load_tool()
    tmp = Path(tempfile.mkdtemp(prefix="r05-r13-demo-"))
    try:
        home = h.make_home(tool, tmp)
        print("СИНТЕТИЧЕСКАЯ ДЕМОНСТРАЦИЯ R05 раунда 13 (example.invalid; реальный пакет не меняется)")
        show("0. Состояния целей до проверки", *h.run(tool, "status"))
        form = h.evidence_form_a(tool)
        form["capture"]["origin"] = "search_summary"
        show("1a. Отказ: пересказ поиска вместо текста страницы", *h.attach_a(tool, home, form))
        snippet = home["texts"] / "snippet.txt"
        snippet.write_text("Улицу Алматы в Астане частично закроют до конца 2026 года. Опубликовано: 18 июля 2026",
                           encoding="utf-8")
        p = h.write(tmp / "f.json", h.evidence_form_a(tool))
        show("1b. Отказ: сниппет, сохранённый как «страница»",
             *h.run(tool, "attach", p, "--text", snippet, "--attached-at", "2026-10-06T10:00:00Z"))
        show("1c. Прикрепление сохранённого текста страницы", *h.attach_a(tool, home))
        show("2a. Отказ: проверяет тот же человек",
             *h.review(tool, home, h.review_form_for(tool, "test-almaty-closure", reviewer="оператор R05 (тест)")))
        show("2b. Проверка другим сотрудником", *h.review(tool, home, h.review_form_for(tool, "test-almaty-closure")))
        code, out = h.run(tool, "build")
        show("3. Сборка пакета черновиков (сводка)", code, out["summary"])
        pkg = json.loads((home["root"] / "package.civic-v1.json").read_text("utf-8"))
        item = dict(pkg["items"][0])
        item["geometry"] = {"type": item["geometry"]["type"], "points": len(item["geometry"]["coordinates"])}
        show("3b. Запись civic-v1 (геометрия сокращена)", 0, item)
        db = tmp / "civic.sqlite3"
        env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "CIVIC_"))}

        def civic(*argv):
            proc = subprocess.run([sys.executable, "-s", "-B", "-m", "ui.civic_store", "--db", str(db), *map(str, argv)],
                                  cwd=args.r02_root, env=env, capture_output=True, text=True, timeout=120)
            try:
                return proc.returncode, json.loads(proc.stdout)
            except ValueError:
                return proc.returncode, (proc.stdout + proc.stderr)[-1500:]
        civic("init")
        pkg_path = home["root"] / "package.civic-v1.json"
        show(f"4a. R02 ({args.r02_root}) import --dry-run", *civic("import", pkg_path, "--dry-run"))
        show("4b. R02 import", *civic("import", pkg_path))
        show("4c. R02 повторный import (стабильный id)", *civic("import", pkg_path))
        ev = home["root"] / "evidence/test-almaty-closure/src-r12-test-almaty-a.json"
        doc = json.loads(ev.read_text("utf-8"))
        doc["notes"] = "дописано после проверки"
        ev.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        show("5. Правка доказательства после проверки -> review_stale", *h.run(tool, "status", "test-almaty-closure"))
        code, out = h.run(tool, "build")
        show("5b. Пересборка: запись выпала из пакета", code,
             {k: out["summary"][k] for k in ("verified_current", "verified_historical", "states")})
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
