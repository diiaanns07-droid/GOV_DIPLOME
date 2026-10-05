"""Unpack research exports and inventory files; never execute imported code."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
COLLECTIONS = {"shymkent": "govtech-results", "astana": "astana-results"}
MAX_TOTAL = 100 * 1024 * 1024


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unpack(archive, depth=0):
    if depth > 3:
        raise ValueError(f"Archive nesting limit: {archive.name}")
    target = archive.parent / ("extracted_" + re.sub(r"[^A-Za-z0-9_-]", "_", archive.stem))
    target = target.resolve()
    if not target.is_relative_to(ROOT):
        raise ValueError("Destination outside workspace")
    pending = []
    seen = set()
    with ZipFile(archive) as zipped:
        if sum(item.file_size for item in zipped.infolist()) > MAX_TOTAL:
            raise ValueError(f"Archive size limit: {archive.name}")
        for item in zipped.infolist():
            name = PurePosixPath(item.filename.replace("\\", "/"))
            mode = item.external_attr >> 16
            if name.is_absolute() or ".." in name.parts or any(":" in p for p in name.parts) or stat.S_ISLNK(mode):
                raise ValueError(f"Unsafe archive member in {archive.name}")
            dest = target.joinpath(*name.parts).resolve()
            if not dest.is_relative_to(target):
                raise ValueError("Member outside extraction directory")
            key = str(dest).casefold()
            if key in seen:
                raise ValueError(f"Duplicate archive member in {archive.name}")
            seen.add(key)
            if item.is_dir():
                continue
            content = zipped.read(item)
            if dest.exists() and dest.read_bytes() != content:
                raise ValueError(f"Refusing to overwrite changed file: {dest.relative_to(ROOT)}")
            pending.append((dest, content))
        for dest, content in pending:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                dest.write_bytes(content)
    for dest, _ in pending:
        if dest.suffix.lower() == ".zip":
            unpack(dest, depth + 1)
    return len(pending)


def audit(extract=False):
    OUT.mkdir(parents=True, exist_ok=True)
    rows, errors, extracted = [], [], 0
    for city, folder in COLLECTIONS.items():
        parent = ROOT / "research" / folder
        for agent in sorted(parent.iterdir()):
            if not agent.is_dir() or not re.match(r"\d{2}_", agent.name):
                continue
            if extract:
                for archive in sorted(agent.glob("*.zip")):
                    try:
                        extracted += unpack(archive)
                    except (ValueError, OSError) as exc:
                        errors.append(str(exc))
            files = sorted(p for p in agent.rglob("*") if p.is_file())
            groups = defaultdict(list)
            invalid_json = []
            for path in files:
                groups[digest(path)].append(path.relative_to(ROOT).as_posix())
                if path.suffix.lower() in {".json", ".geojson", ".jsonl"}:
                    try:
                        raw = path.read_text(encoding="utf-8-sig")
                        if path.suffix.lower() == ".jsonl":
                            for line in raw.splitlines():
                                if line.strip():
                                    json.loads(line)
                        else:
                            json.loads(raw)
                    except (ValueError, UnicodeError) as exc:
                        invalid_json.append({"path": path.relative_to(ROOT).as_posix(), "error": str(exc)})
            reports = [p for p in files if re.search(r"_report(?: \(\d+\))?\.md$", p.name, re.I)]
            evidence = [p for p in files if re.search(r"_evidence(?: \(\d+\))?\.json$", p.name, re.I)]
            item = {
                "city": city, "agent": agent.name,
                "status": "complete_files" if reports and evidence else "partial" if files else "missing",
                "reports": [p.relative_to(ROOT).as_posix() for p in reports],
                "evidence": [p.relative_to(ROOT).as_posix() for p in evidence],
                "file_count": len(files), "invalid_json": invalid_json,
                "duplicate_groups": [v for v in groups.values() if len(v) > 1],
                "files": [{"path": p.relative_to(ROOT).as_posix(), "bytes": p.stat().st_size, "sha256": digest(p)} for p in files],
            }
            rows.append(item)
    inventory = {"scope": "Local files only; source claims and imported code have not been independently verified", "agents": rows, "extraction_errors": errors}
    (OUT / "INVENTORY.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    status = ["Инвентаризация сохранённых результатов", "", "Проверены наличие файлов и синтаксис JSON. Факты по ссылкам и присланные эксперименты ещё не перепроверены.", ""]
    for city in COLLECTIONS:
        subset = [r for r in rows if r["city"] == city]
        status.append(f"{city}: отчёты {sum(bool(r['reports']) for r in subset)}/14; evidence {sum(bool(r['evidence']) for r in subset)}/14")
        for r in subset:
            if r["status"] != "complete_files":
                status.append(f"  {r['agent']}: {r['status']}; report={bool(r['reports'])}, evidence={bool(r['evidence'])}")
            if r["invalid_json"]:
                status.append(f"  {r['agent']}: некорректных JSON: {len(r['invalid_json'])}")
            if r["duplicate_groups"]:
                status.append(f"  {r['agent']}: групп одинаковых файлов: {len(r['duplicate_groups'])}; оригиналы сохранены")
    status += ["", "Ошибки распаковки: " + str(len(errors)), *errors, "", "Архивы сохранены. Распакованные файлы находятся в extracted_* рядом с архивами.", "*.zip исключены корневым .gitignore; для совместной работы нужны распакованные файлы."]
    (OUT / "STATUS.txt").write_text("\n".join(status) + "\n", encoding="utf-8")
    print("\n".join(status))
    return 1 if errors else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--extract", action="store_true")
    raise SystemExit(audit(parser.parse_args().extract))
