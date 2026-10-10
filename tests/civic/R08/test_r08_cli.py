"""R08: командная строка python -m ui.civic_akim не падает в консоли Windows с CP1251 (как R10 B-028 у R06)."""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def run(*args, encoding="cp1251"):
    env = dict(os.environ, PYTHONIOENCODING=encoding, PYTHONUTF8="0")
    return subprocess.run([sys.executable, "-m", "ui.civic_akim", *args], cwd=ROOT, env=env,
                          capture_output=True, timeout=120)


def test_kazakh_text_in_cp1251_console_does_not_crash():
    out = run("--lang", "kk")
    assert out.returncode == 0, out.stderr.decode("cp1251", "replace")[-500:]
    assert "Traceback" not in out.stderr.decode("cp1251", "replace")


def test_json_in_cp1251_console_stays_valid_and_keeps_kazakh_letters():
    out = run("--json")
    assert out.returncode == 0, out.stderr.decode("cp1251", "replace")[-500:]
    data = json.loads(out.stdout.decode("cp1251"))
    assert data["text"]["kk"] and "?" not in data["text"]["kk"]
    assert any(ch in data["text"]["kk"] for ch in "әғқңөұүһі"), "казахские буквы не потерялись"


def test_utf8_console_prints_kazakh_as_is():
    out = run("--lang", "kk", encoding="utf-8")
    assert out.returncode == 0
    assert any(ch in out.stdout.decode("utf-8") for ch in "әғқңөұүһі")
