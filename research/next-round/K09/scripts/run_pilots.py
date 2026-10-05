"""K09: воспроизведение пилотов A13/AST-A13 без изменения оригиналов.

Каждый оригинальный скрипт читается как текст. Жёсткий путь `/home/claude/stupits`
заменяется на корень этого репозитория, копия выполняется во временной папке,
stdout сохраняется в research/next-round/K09/repro/<id>_stdout.json.
Сеть не используется. Скрипты только читают data/*.json и вызывают engine/agent.

Запуск из корня репозитория (Python 3.12 + numpy 2.4.4 + jsonschema 4.26.0):
    python research/next-round/K09/scripts/run_pilots.py [E4] [E5] [E6]
"""
import hashlib, json, platform, subprocess, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "research/next-round/K09/repro"
A13 = ROOT / "research/govtech-results/13_architecture_ai_thesis/extracted_files__21_"
AST = ROOT / "research/astana-results/13_architecture_ai_thesis/extracted_files__34_"
PILOTS = {
    "E4": (A13 / "constraints_eval.py", A13 / "constraints_eval_result.json"),
    "E5": (AST / "kk_numeral_filter.py", AST / "kk_numeral_filter_result.json"),
    "E6": (AST / "rank_sensitivity.py", AST / "rank_sensitivity_result.json"),
}


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main(ids):
    OUT.mkdir(parents=True, exist_ok=True)
    git = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    for pid in ids:
        src, reported = PILOTS[pid]
        code = src.read_text(encoding="utf-8").replace("/home/claude/stupits", str(ROOT))
        with tempfile.TemporaryDirectory() as tmp:
            tmp_script = Path(tmp) / src.name
            tmp_script.write_text(code, encoding="utf-8")
            t0 = time.perf_counter()
            run = subprocess.run([sys.executable, str(tmp_script)], cwd=str(ROOT), capture_output=True, text=True)
            secs = round(time.perf_counter() - t0, 1)
        (OUT / f"{pid}_stdout.json").write_text(run.stdout, encoding="utf-8")
        meta = {"pilot": pid, "script": str(src.relative_to(ROOT)), "script_sha256": sha(src),
                "reported_result": str(reported.relative_to(ROOT)), "reported_sha256": sha(reported),
                "city_data_sha256": sha(ROOT / "data/city_data.json"), "repo_head": git,
                "python": platform.python_version(), "returncode": run.returncode,
                "stderr_tail": run.stderr[-2000:], "wall_seconds": secs,
                "path_substitution": "/home/claude/stupits -> repo root (только в копии)"}
        try:
            import numpy, importlib.metadata as md
            meta["numpy"] = numpy.__version__
            meta["jsonschema"] = md.version("jsonschema")
        except Exception as e:  # noqa: BLE001
            meta["versions_error"] = repr(e)
        (OUT / f"{pid}_run_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(pid, "rc", run.returncode, "sec", secs)


if __name__ == "__main__":
    main(sys.argv[1:] or list(PILOTS))
