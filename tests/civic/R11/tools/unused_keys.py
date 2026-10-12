"""R11 · ключи словаря, которых не использует ни одна ветка (отчёт к заморозке FINAL-2; ничего не удаляет).

    python3 tests/civic/R11/tools/unused_keys.py origin/claude/sharp-dijkstra-0t87gl origin/claude/r14-R05 … > отчёт.md
Ключ считается используемым, если в коде любой ветки (web/, ui/, engine/, ml/ — .js .mjs .html .py) встречается
строка с этим ключом целиком или префикс, к которому ключ дописывается в коде («"subtopic." + id», `heat.kind.${k}`).
Свои пути R11 (витрина ui-kit, макеты) берутся из рабочей копии (HEAD).
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DICT = json.loads((ROOT / "web/civic/i18n/ru.json").read_text("utf-8"))
KEYS = set(DICT)
STR = re.compile(r"""["'`]([a-z][a-z0-9_]*(?:\.[a-z0-9_]*)+\.?)(?:\$\{|["'`])""")
EXT = (".js", ".mjs", ".html", ".py")


def ref_files(ref):
    out = subprocess.run(["git", "ls-tree", "-r", "--name-only", ref, "--", "web", "ui", "engine", "ml"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout.split()
    return [f for f in out if f.endswith(EXT) and "/vendor/" not in f and "/i18n/" not in f and "/tests/" not in f
            and "/ui-kit/" not in f]  # ui-kit — из рабочей копии R11


def scan(text, used, prefixes):
    for s in STR.findall(text):
        if s in KEYS:
            used.add(s)
        elif s.endswith(".") and any(k.startswith(s) for k in KEYS):
            prefixes.add(s)


def main(argv):
    refs = argv[1:]
    used, prefixes, texts = set(), set(), []
    for ref in refs:
        for f in ref_files(ref):
            texts.append(subprocess.run(["git", "show", f"{ref}:{f}"], cwd=ROOT, capture_output=True, text=True).stdout)
    for f in list((ROOT / "web/civic/ui-kit").rglob("*")) + [ROOT / "web/civic/i18n/i18n.js"]:
        if f.suffix in (".js", ".html"):
            texts.append(f.read_text("utf-8", errors="ignore"))
    for t in texts:
        scan(t, used, prefixes)
    # Осторожно: ключ, который хоть где-то встречается текстом (data-i18n-attr="title:ключ", шаблоны), — используемый.
    big = "\n".join(texts)
    used |= {k for k in KEYS if k in big}
    unused = sorted(k for k in KEYS if k not in used and not any(k.startswith(p) for p in prefixes))
    groups = {}
    for k in unused:
        groups.setdefault(k.split(".")[0], []).append(k)
    print(f"# Ключи словаря без использования — {len(unused)} из {len(KEYS)}\n")
    print("Ветки: " + ", ".join(f"`{r}`" for r in refs) + " + ui-kit R11 (HEAD).")
    print("Динамические префиксы (ключ дописывается в коде): " + ", ".join(f"`{p}`" for p in sorted(prefixes)) + "\n")
    print("Перед удалением — проверить глазами: ключ может собираться из частей иначе, чем видит этот поиск.\n")
    for g in sorted(groups):
        print(f"- **{g}** ({len(groups[g])}): " + ", ".join(f"`{k}`" for k in groups[g]))
    print(f"\n— не используется: {len(unused)}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv)
