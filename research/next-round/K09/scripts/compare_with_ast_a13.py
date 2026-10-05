"""K09: сверка SHA-256 файлов, полученных K09, с SHA256SUMS.txt агента AST-A13.

Запуск из корня репозитория:
    python3 research/next-round/K09/scripts/compare_with_ast_a13.py
Читает только два текстовых файла хэшей; сеть не использует.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
AST = ROOT / "research/astana-results/13_architecture_ai_thesis/extracted_files__34_/SHA256SUMS.txt"
K09 = ROOT / "research/next-round/K09/sources/SHA256SUMS.txt"


def load(path):
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, name = line.split(maxsplit=1)
            out[name.strip()] = digest
    return out


ast, k09 = load(AST), load(K09)
match = differ = only_ast = 0
for name, digest in sorted(ast.items()):
    repo, fname = name.split(".", 1)  # AST-A13: "Owner_repo.FILE"
    cand = [k for k in k09 if k.startswith(repo + "/") and k.endswith(fname)]
    if not cand:
        only_ast += 1
        print(f"ONLY_AST {name}")
    elif k09[cand[0]] == digest:
        match += 1
        print(f"MATCH    {name} <-> {cand[0]}")
    else:
        differ += 1
        print(f"DIFFER   {name} <-> {cand[0]}")
print(f"match={match} differ={differ} only_ast={only_ast}")
