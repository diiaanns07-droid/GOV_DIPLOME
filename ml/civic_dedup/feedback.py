"""Журнал решений акимата о дублях (волна мелочей п. 9, R04): что объединили, что разделили.

Зачем. «Похоже на» (R04 /similar) предлагает жителю «Я тоже», сотрудник сам отмечает дубли. Когда акимат нажимает
«Это разные проблемы» (R09 separate), это честная разметка: пара обращений — РАЗНЫЕ. Отметка «дубль» — пара
ОДИНАКОВЫЕ. Журнал копит такие пары и оценку модели для каждой. По нему видно, как часто подсказка ошибается,
и на нём — уже на настоящих обращениях, а не на синтетике R02 — потом проверяют и подбирают порог (tune).

Что пишем: id обеих жалоб, решение, источник, оценку модели и порог в момент решения. Тексты жителей в журнал
НЕ пишутся — они остаются в хранилище R09; export() соединяет журнал с базой только на ноутбуке владельца.
Где: <папка базы жалоб>/dedup_feedback.jsonl (по умолчанию .runtime/, она вне Git) или путь CIVIC_DEDUP_FEEDBACK.

    python -m ml.civic_dedup.feedback stats  --log .runtime/dedup_feedback.jsonl
    python -m ml.civic_dedup.feedback export --log .runtime/dedup_feedback.jsonl --db .runtime/civic.sqlite3 \\
        --out pairs_real.jsonl          # пары в формате R02 (a, b, same_incident, kind, split) для tune
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

LOGGER = logging.getLogger(__name__)
ENV_PATH = "CIVIC_DEDUP_FEEDBACK"
FILE_NAME = "dedup_feedback.jsonl"
SAME, DIFFERENT = "same", "different"


class FeedbackLog:
    """Дописываемый JSONL (одна строка — одно решение) + счётчики в памяти. Потокобезопасно."""

    def __init__(self, path=None):
        self.path = Path(path) if path else None
        self._lock = threading.Lock()
        self._rows: list[dict] = []
        if self.path and self.path.exists():
            try:
                self._rows = [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines()
                              if line.strip()]
            except (OSError, ValueError):
                LOGGER.warning("журнал решений о дублях не прочитан: %s", self.path)
                self._rows = []

    def record(self, a: str, b: str, decision: str, source: str, *, score=None, threshold=None, method=None,
               at: str | None = None) -> dict:
        row = {"at": at or datetime.now(timezone.utc).replace(microsecond=0).isoformat(), "decision": decision,
               "source": source, "a": a, "b": b,
               "score": None if score is None else round(float(score), 4),
               "threshold": None if threshold is None else round(float(threshold), 4), "method": method}
        with self._lock:
            self._rows.append(row)
            if self.path:
                try:
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    with open(self.path, "a", encoding="utf-8") as fh:
                        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                except OSError:
                    LOGGER.exception("журнал решений о дублях: запись не удалась")
        return row

    def rows(self) -> list[dict]:
        with self._lock:
            return list(self._rows)

    def stats(self) -> dict:
        """Сколько объединений подтверждено и сколько разделено; сколько разделённых пар модель сочла похожими."""
        rows = self.rows()
        different = [r for r in rows if r["decision"] == DIFFERENT]
        above = [r for r in different if r.get("score") is not None and r.get("threshold") is not None
                 and r["score"] >= r["threshold"]]
        return {"same": sum(1 for r in rows if r["decision"] == SAME), "different": len(different),
                "different_model_said_same": len(above), "path": str(self.path) if self.path else None}


def default_path(db_path) -> Path | None:
    """Путь журнала: CIVIC_DEDUP_FEEDBACK или рядом с базой жалоб; база в памяти — без файла."""
    env = os.environ.get(ENV_PATH)
    if env:
        return Path(env)
    if not db_path or str(db_path) == ":memory:":
        return None
    return Path(db_path).resolve().parent / FILE_NAME


def export_pairs(log_rows: list[dict], db_path) -> list[dict]:
    """Пары для tune в формате R02 из журнала и базы R09 (тексты — только здесь, на машине владельца).
    Последнее решение по паре главнее (сначала «дубль», потом «разные» -> разные)."""
    latest: dict[tuple, dict] = {}
    for row in log_rows:
        latest[tuple(sorted((row["a"], row["b"])))] = row
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        def text(cid):
            found = con.execute("SELECT record_json FROM complaints_v2 WHERE id = ?", (cid,)).fetchone()
            return json.loads(found[0]).get("text") if found else None

        out = []
        for (a, b), row in latest.items():
            ta, tb = text(a), text(b)
            if ta and tb:
                out.append({"a": ta, "b": tb, "same_incident": row["decision"] == SAME, "kind": "akimat_decision",
                            "split": "real", "source": row["source"], "lang_a": "?", "lang_b": "?"})
        return out
    finally:
        con.close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ml.civic_dedup.feedback")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("stats")
    s.add_argument("--log", required=True)
    e = sub.add_parser("export")
    e.add_argument("--log", required=True)
    e.add_argument("--db", required=True)
    e.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    log = FeedbackLog(args.log)
    if args.cmd == "stats":
        print(json.dumps(log.stats(), ensure_ascii=False, indent=1))
        return 0
    pairs = export_pairs(log.rows(), args.db)
    with open(args.out, "w", encoding="utf-8") as fh:
        for pair in pairs:
            fh.write(json.dumps(pair, ensure_ascii=False) + "\n")
    print(f"пар: {len(pairs)} -> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
