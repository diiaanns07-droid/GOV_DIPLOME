"""R11 · ключи i18n, которые модуль роли уже использует, а в общем словаре R11 их нет.

Читает код прямо из git-ссылки (ветка роли или сборки R01), ничего не запускает:
    python3 tests/civic/R11/tools/missing_keys.py origin/claude/r14-R05 web/civic/build3d [ещё пути…]
Ищет t("…")/tr("…")/T("…"), data-t="…", data-i18n="…" и определения "ключ": в запасных словарях модулей.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DICT = json.loads((ROOT / "web/civic/i18n/ru.json").read_text("utf-8"))
KEY = r"[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+"
PATTERNS = [
    re.compile(r"""\b(?:t|tr|tt|T|_t|t2)\(\s*["'](%s)["']""" % KEY),
    re.compile(r"""data-(?:t|i18n)(?:-attr)?=["'](?:[a-z-]+:)?(%s)""" % KEY),
    re.compile(r"""^\s*["'](%s)["']\s*:""" % KEY, re.M),
]
SKIP = re.compile(r"\.(js|json|css|html|png|svg)$|^(budget|schedule|responsible|source|geometry|evidence)\.")


def files(ref, paths):
    out = subprocess.run(["git", "ls-tree", "-r", "--name-only", ref, "--", *paths], cwd=ROOT, capture_output=True, text=True, check=True)
    return [f for f in out.stdout.split() if f.endswith((".js", ".mjs", ".html")) and "/vendor/" not in f and "/i18n/" not in f]


def main(argv):
    ref, paths = argv[1], argv[2:] or ["web"]
    missing = {}
    for f in files(ref, paths):
        text = subprocess.run(["git", "show", f"{ref}:{f}"], cwd=ROOT, capture_output=True, text=True).stdout
        for pat in PATTERNS:
            for k in pat.findall(text):
                if k not in DICT and not SKIP.search(k):
                    missing.setdefault(k, set()).add(f)
    for k in sorted(missing):
        print(k, "·", ", ".join(sorted(missing[k])))
    print(f"— нет в словаре: {len(missing)}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv)
