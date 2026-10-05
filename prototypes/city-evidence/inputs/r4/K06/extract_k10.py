"""Extract the K10 round-3 package byte-exactly from git (no text pipeline) and verify SHA256 vs its manifest.
Usage (from the repo root, after `git fetch origin claude/save-work-handoff-j7pc05`):
  python3 research/round-4-results/K06/extract_k10.py <out_dir>"""
import hashlib, json, pathlib, subprocess, sys
SHA = "ea703f1ddd3a411430a981164a78a7dda64ec909"
P = "research/round-3-results/K10"
out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
show = lambda path: subprocess.check_output(["git", "show", f"{SHA}:{P}/{path}"])
mb = show("package_manifest.json"); (out / "package_manifest.json").write_bytes(mb)
man, ok = json.loads(mb), True
for city, cm in man["cities"].items():
    for name, f in cm["files"].items():
        b = show(f["path"]); p = out / f["path"]; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b)
        good = hashlib.sha256(b).hexdigest() == f["sha256"] and len(b) == f["bytes"]
        ok &= good
        print(city, name, f["sha256"][:12], "OK" if good else "MISMATCH")
sys.exit(0 if ok else 1)
