"""Round 13: статические проверки фронтенда и запрет автоматического экспорта сообщений.

Разбор ссылки квитанции проверяется в Node (vm) на настоящем feedback.js без браузера.
"""

import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[3]
JS = (ROOT / "web/civic/feedback/feedback.js").read_text(encoding="utf-8")


def code_only(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", source)


def test_staff_hint_never_formats_model_score():
    code = code_only(JS)
    assert "sug.score" not in code and "toFixed(2) + \" (\" + (sug.score_kind" not in code
    assert "Числовая оценка модели не показывается" in JS
    assert "синтетических" in JS                    # предупреждение о демо-модели


def test_public_api_round13():
    for name in ("mountReceipt: mountReceipt", "receiptFromLocation: receiptFromLocation", "clearDrafts: clearDrafts"):
        assert name in JS


def test_browser_storage_is_tab_scoped_and_prefixed():
    code = code_only(JS)
    assert "localStorage" not in code and "document.cookie" not in code and "indexedDB" not in code
    keys = set(re.findall(r'"(civic-r06-[a-z]+:)"', code))
    assert keys == {"civic-r06-draft:", "civic-r06-receipts:"}
    staff_part = code.split("function mountModeration")[1]
    assert "sessionStorage" not in staff_part           # кабинет сотрудника — только память страницы


def test_receipt_number_travels_in_fragment_or_body_only():
    code = code_only(JS)
    assert '"#" + RECEIPT_HASH + "="' in code            # ссылка — #фрагмент
    assert "?receipt" not in code and "receipt_id=" not in code
    assert code.count('"/feedback/receipt", { receipt_id: id }') == 1


NODE_PROBE = r"""
const vm = require("vm");
const fs = require("fs");
const store = new Map();
const sessionStorage = {
  get length() { return store.size; }, key: (i) => Array.from(store.keys())[i] ?? null,
  getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
};
const window = { location: { hash: "", origin: "http://127.0.0.1:8611", pathname: "/", search: "" }, sessionStorage };
vm.createContext(Object.assign(window, { window }));
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), window);
const api = window.CivicFeedback;
const id = "fbr_" + "Ab9_-".repeat(5);
const out = {};
for (const [name, hash] of Object.entries({
  plain: "#civic-receipt=" + id, combined: "#object=demo-1&civic-receipt=" + id, encoded: "#civic-receipt=" + encodeURIComponent(id),
  short: "#civic-receipt=fbr_short", injected: "#civic-receipt=" + id + "%3Cscript%3E", other: "#object=demo-1", broken: "#civic-receipt=%E0%A4%A",
})) { out[name] = api.receiptFromLocation(hash); }
store.set("civic-r06-draft:object:x", "{}"); store.set("civic-r06-receipts:object:x", "{}"); store.set("other-app", "1");
api.clearDrafts();
out.left = Array.from(store.keys());
console.log(JSON.stringify(out));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node не установлен")
def test_receipt_link_parsing_and_clear_drafts_in_node():
    result = subprocess.run(["node", "-e", NODE_PROBE, str(ROOT / "web/civic/feedback/feedback.js")],
                            check=True, capture_output=True, text=True)
    out = json.loads(result.stdout)
    receipt = "fbr_" + "Ab9_-" * 5
    assert out["plain"] == out["combined"] == out["encoded"] == receipt
    assert out["short"] is None and out["injected"] is None and out["other"] is None and out["broken"] is None
    assert out["left"] == ["other-app"]                    # чужие ключи вкладки не трогаются


def test_no_automatic_export_of_messages():
    """Модуль не пишет тексты в файлы, не отправляет их в сеть и не готовит датасет."""
    for path in (ROOT / "ui/civic_feedback").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for pattern in (r"open\([^)]*['\"][wa]", r"\.write_text\(", r"urllib\.request", r"http\.client", r"requests\.",
                        r"socket\.", r"csv\.writer", r"to_csv", r"jsonl"):
            assert not re.search(pattern, source), (path.name, pattern)
