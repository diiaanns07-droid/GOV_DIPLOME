#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K05 round 3: regression-тест fetch_real_context.handle_failure() во временном каталоге.

Контракт (что должно быть после интеграции patches/fetch_real_context_null_on_failure.patch):
  1. Нет предыдущих данных → в real_context.json null во всех ячейках (не 0),
     meta.status = "unavailable", meta.last_attempt.status = "failed".
  2. Есть предыдущий успешный результат → данные и status/generated_at не меняются,
     но meta.last_attempt фиксирует неудачную попытку и ошибку.
  3. Есть данные, но meta не читается → meta восстанавливается со status="unknown"
     и last_attempt.

PatchedCopy — копия продукта во временном каталоге с применённым patch: должна проходить.
CurrentProduct — текущий fetch_real_context.py без изменений: отмечен expectedFailure,
пока patch не интегрирован (после интеграции unittest покажет unexpected success —
тогда декоратор нужно снять).

Сеть не используется: вызывается только handle_failure(). Файлы data/ не трогаются.
Запуск из корня репозитория:
    python research/round-3-results/K05/regression/test_handle_failure.py
"""

import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PRODUCT = ROOT / "fetch_real_context.py"
PATCH = HERE.parent / "patches" / "fetch_real_context_null_on_failure.patch"


def load_module(src: Path, workdir: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # только определения; main() не вызывается
    mod.ROOT = workdir
    mod.OUT_PATH = workdir / "data" / "real_context.json"
    mod.META_PATH = workdir / "data" / "real_context_meta.json"
    mod.POINTS_PATH = workdir / "data" / "real_context_points.geojson"
    return mod


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class Contract:
    """Сценарии; подкласс задаёт self.src — путь к проверяемому fetch_real_context.py."""

    src: Path

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.work = Path(self._tmp.name)
        self.mod = load_module(self.src, self.work, f"frc_{type(self).__name__}")

    def tearDown(self):
        self._tmp.cleanup()

    def test_no_previous_data_writes_null_not_zero(self):
        self.assertEqual(self.mod.handle_failure("тест: Overpass недоступен", "osm"), 1)
        cells = [v for d in read(self.mod.OUT_PATH).values() for v in d.values()]
        self.assertEqual(len(cells), 25)
        self.assertTrue(all(v is None for v in cells), f"ожидались null, получено {set(cells)}")
        meta = read(self.mod.META_PATH)
        self.assertEqual(meta["status"], "unavailable")
        self.assertEqual(meta["last_attempt"]["status"], "failed")
        self.assertIn("Overpass", meta["last_attempt"]["error"])

    def test_previous_success_kept_and_failed_attempt_recorded(self):
        ok_counts = {d: {c: i for i, c in enumerate(self.mod.CATEGORIES)} for d in self.mod.DISTRICT_IDS}
        self.mod.write_json(self.mod.OUT_PATH, ok_counts)
        ok_meta = self.mod.make_meta("ok", "osm", osm_elements=123)
        self.mod.write_json(self.mod.META_PATH, ok_meta)
        self.assertEqual(self.mod.handle_failure("тест: второй сбой", "osm"), 1)
        self.assertEqual(read(self.mod.OUT_PATH), ok_counts)
        meta = read(self.mod.META_PATH)
        self.assertEqual(meta["status"], "ok")
        self.assertEqual(meta["generated_at"], ok_meta["generated_at"])
        self.assertEqual(meta["last_attempt"]["status"], "failed")
        self.assertEqual(meta["last_attempt"]["error"], "тест: второй сбой")

    def test_previous_data_with_unreadable_meta(self):
        self.mod.write_json(self.mod.OUT_PATH, {"esil": {"schools": 3}})
        self.mod.META_PATH.write_text("{битый json", encoding="utf-8")
        self.mod.handle_failure("тест: сбой", "osm")
        meta = read(self.mod.META_PATH)
        self.assertEqual(meta["status"], "unknown")
        self.assertEqual(meta["last_attempt"]["status"], "failed")


class PatchedCopy(Contract, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._ptmp = tempfile.TemporaryDirectory()
        d = Path(cls._ptmp.name)
        shutil.copy2(PRODUCT, d / "fetch_real_context.py")
        res = subprocess.run(["patch", "-p1", "--batch", "-d", str(d), "-i", str(PATCH)],
                             capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"patch не применился: {res.stdout}{res.stderr}")
        cls.src = d / "fetch_real_context.py"

    @classmethod
    def tearDownClass(cls):
        cls._ptmp.cleanup()


def _expected_failure(func):
    """expectedFailure на отдельной обёртке: флаг не должен попасть в общий метод Contract."""
    def wrapper(self):
        return func(self)
    wrapper.__name__ = func.__name__
    return unittest.expectedFailure(wrapper)


class CurrentProduct(Contract, unittest.TestCase):
    src = PRODUCT

    # До интеграции patch текущий код нарушает контракт (пишет 0, не пишет last_attempt).
    test_no_previous_data_writes_null_not_zero = _expected_failure(
        Contract.test_no_previous_data_writes_null_not_zero)
    test_previous_success_kept_and_failed_attempt_recorded = _expected_failure(
        Contract.test_previous_success_kept_and_failed_attempt_recorded)
    test_previous_data_with_unreadable_meta = _expected_failure(
        Contract.test_previous_data_with_unreadable_meta)


if __name__ == "__main__":
    unittest.main(verbosity=2)
