"""D01/D02: find round-11 DELIVERY.json files on origin branches and check them (no checkout).

  git fetch origin && python3 -I -B tests/civic/R10/delivery_scan.py \
      --out research/round-11-results/R10/DELIVERIES_SCAN.json

For every origin/* branch and every research/round-11-results/RNN/DELIVERY.json found:
contract shape (check_delivery), pack_sha, whether code_commit exists and is an ancestor
of the branch head, whether the role's STATUS.md and owned paths exist at that head,
and for R01 whether MATRIX.json / RUN.txt exist. A delivery is a claim, not a result.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from r10lib.contract import check_delivery  # noqa: E402

PACK_SHA = "9c2f5c0dae14b46c0697a9dfc7f854351bfd570d"
REPO = HERE.parents[2]


def git(*args, check=False) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, check=check)


def show(ref: str, path: str) -> str | None:
    r = git("show", f"{ref}:{path}")
    return r.stdout if r.returncode == 0 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    branches = [b.strip() for b in git("branch", "-r", "--format=%(refname:short)").stdout.splitlines()
                if b.strip() and not b.strip().endswith("/HEAD")]
    found = []
    for br in branches:
        head = git("rev-parse", br).stdout.strip()
        listing = git("ls-tree", "-r", "--name-only", br, "research/round-11-results/").stdout.split()
        for path in listing:
            parts = path.split("/")
            if len(parts) != 4 or parts[3] != "DELIVERY.json":
                continue
            role = parts[2]
            raw = show(br, path)
            entry = {"branch": br, "head": head, "path": path, "role_dir": role,
                     "head_time": git("log", "-1", "--format=%cI", br).stdout.strip()}
            try:
                doc = json.loads(raw or "")
            except ValueError as exc:
                entry.update(valid_json=False, problems=[f"invalid JSON: {exc}"])
                found.append(entry)
                continue
            problems = check_delivery(doc, role=role, pack_sha=PACK_SHA)
            code = doc.get("code_commit")
            code_info = None
            if code:
                exists = git("cat-file", "-e", f"{code}^{{commit}}").returncode == 0
                ancestor = exists and git("merge-base", "--is-ancestor", code, head).returncode == 0
                code_info = {"sha": code, "exists": exists, "ancestor_of_head": ancestor}
                if not exists:
                    problems.append(f"code_commit {code} not found in fetched objects")
            status_md = f"research/handoffs/astana/{role}/round-11/STATUS.md"
            owned = {p: bool(git("ls-tree", "--name-only", br, p.rstrip("/")).stdout.strip())
                     for p in doc.get("owned_paths") or []}
            extras = {}
            if role == "R01":
                for name in ("MATRIX.json", "RUN.txt", "DEMO.txt", "CODE_SHA", "CODE_SHA.txt"):
                    extras[name] = show(br, f"research/round-11-results/R01/{name}") is not None
            entry.update(valid_json=True, role=doc.get("role"), status=doc.get("status"),
                         pack_sha=doc.get("pack_sha"), code_commit=code_info,
                         checks=[{k: c.get(k) for k in ("name", "status")} for c in doc.get("checks") or []
                                 if isinstance(c, dict)],
                         status_md_present=show(br, status_md) is not None,
                         owned_paths_present=owned, r01_files=extras or None,
                         next_step=doc.get("next_step"), problems=problems)
            found.append(entry)
    out = {"scanned_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "pack_sha": PACK_SHA, "branches_scanned": len(branches),
           "deliveries": sorted(found, key=lambda e: (e["role_dir"], e["head_time"]))}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for e in out["deliveries"]:
        print(f"{e['role_dir']:4} {e['branch']:45} {e['head'][:8]} status={e.get('status')} "
              f"code={((e.get('code_commit') or {}).get('sha') or '-')[:8]} problems={len(e.get('problems', []))}")
    print(f"{len(found)} deliveries on {len(branches)} branches")


if __name__ == "__main__":
    main()
