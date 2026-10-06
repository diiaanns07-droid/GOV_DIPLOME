"""Интеграционная проверка R09 на реальном коде соседей (без изменения их веток).

    python3 research/round-11-results/R09/check_r02_r07_integration.py --r02 <checkout R02> --r07 <checkout R07>

Собирает во временном каталоге «ферму» симлинков: ui -> R02/ui, engine -> R07/engine,
agent -> этот репозиторий/agent. Затем: временная SQLite R02, одноразовый редактор со
случайным паролем (нигде не сохраняется), черновик -> публикация -> перенос срока с
причиной -> ответы помощника через r02_public_loader и AssistantEndpoint; сценарий —
r07_case_loader с настоящим compare(). Печатает JSON {checks:[...]}.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve()
REPO = HERE.parents[3]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--r02", required=True)
    ap.add_argument("--r07", required=True)
    args = ap.parse_args()
    tmp = Path(tempfile.mkdtemp(prefix="r09-integ-"))
    farm = tmp / "farm"
    farm.mkdir()
    (farm / "ui").symlink_to(Path(args.r02).resolve() / "ui")
    (farm / "engine").symlink_to(Path(args.r07).resolve() / "engine")
    (farm / "agent").symlink_to(REPO / "agent")
    sys.path.insert(0, str(farm))

    from ui.civic_store.service import CivicService
    from engine.civic_scenarios.compare import compare
    from engine.civic_scenarios.registry import list_cases, load_graph
    from agent.civic_assistant import build_verified_context
    from agent.civic_assistant.api import AssistantEndpoint, RateLimiter, r02_public_loader, r07_case_loader

    checks = []

    def rec(name, ok, detail=""):
        checks.append({"name": name, "status": "PASS" if ok else "FAIL", "detail": str(detail)[:300]})

    svc = CivicService(tmp / "civic.sqlite3")
    password = secrets.token_urlsafe(18)  # одноразовый, только в памяти процесса
    svc.accounts.create_user("r09check", password, display_name="R09 check", public_label="Редакция (проверка R09)")

    def call(method, path, body=None, cookie=None, csrf=None):
        headers = {"Host": "127.0.0.1:8501"}
        if cookie:
            headers["Cookie"] = cookie
        if csrf:
            headers["X-CSRF-Token"] = csrf
        raw = json.dumps(body).encode("utf-8") if body is not None else None
        return svc.handle(method, "/api/civic/v1" + path, {}, raw,
                          {"headers": headers, "client_ip": "127.0.0.1", "host_allowed": True, "is_same_origin": True,
                           "is_https": False})

    login = call("POST", "/session/login", {"username": "r09check", "password": password})
    cookie = login["headers"].get("Set-Cookie", "").split(";", 1)[0]
    csrf = login["body"]["data"]["csrf_token"]
    rec("r02_login", login["status"] == 200 and bool(cookie))

    pack = json.loads((REPO / "tests/civic/R09/fixtures/pack_civic_object.json").read_text(encoding="utf-8"))
    body = {k: v for k, v in pack.items() if k not in ("schema_version", "id", "city", "publication", "updated_at",
                                                        "revision")}
    created = call("POST", "/staff/objects", body, cookie, csrf)
    rec("r02_create_draft", created["status"] == 201, created["status"])
    item = created["body"]["data"]["item"]
    oid = item["id"]

    load = r02_public_loader(svc)
    endpoint = AssistantEndpoint(load, r07_case_loader(list_cases, load_graph, compare),
                                 rate_limiter=RateLimiter(1000, 60))

    def ask(question, object_id=oid, scenario_id=None):
        resp = endpoint.handle("POST", "/api/civic/v1/assistant", {},
                               {"question": question, "object_id": object_id, "scenario_id": scenario_id},
                               {"client_ip": "127.0.0.1", "headers": {}})
        return resp["body"]["data"]

    rec("draft_not_visible_to_assistant", load(oid) is None and ask("Что здесь?")["source"] == "unavailable")

    pub = call("POST", f"/staff/objects/{oid}/publish", {"expected_revision": item["revision"],
                                                          "reason": "Публикация синтетической записи (проверка R09)"},
               cookie, csrf)
    rec("r02_publish", pub["status"] == 200, pub["status"])
    item = pub["body"]["data"]["item"]
    loaded = load(oid)
    rec("public_loader_returns_item_and_history", bool(loaded) and loaded[0]["id"] == oid
        and isinstance(loaded[1], list), None if not loaded else [h.get("revision") for h in loaded[1]])
    try:
        ctx = build_verified_context(*loaded)
        rec("r02_public_dto_accepted_by_facts", True, ctx["warnings"])
    except Exception as exc:  # noqa: BLE001
        rec("r02_public_dto_accepted_by_facts", False, repr(exc))
    a = ask("Когда закончат?")
    rec("answer_from_r02_object", a["source"] == "template" and "22.10.2026" in a["text"] and "синтетическая" in a["text"],
        a["text"][:200])

    schedule = dict(item["schedule"], current_planned_end="2026-10-29")
    upd = call("POST", f"/staff/objects/{oid}/update",
               {"expected_revision": item["revision"], "changes": {"schedule": schedule},
                "reason": "СЛУЖЕБНАЯ причина правки (не для жителей, проверка R09)"}, cookie, csrf)
    rec("r02_update_schedule", upd["status"] == 200, upd["status"] if upd["status"] == 200 else upd["body"])
    item = upd["body"]["data"]["item"] if upd["status"] == 200 else item
    # До повторной публикации правка редактора не должна быть видна помощнику жителя.
    a = ask("Когда закончат?")
    rec("unpublished_staff_change_not_visible", "22.10.2026" in a["text"] and "29.10.2026" not in a["text"], a["text"][:160])
    # В R02 публичная история содержит только события публикации: публичное объяснение переноса
    # редактор пишет в reason публикации; reason промежуточной правки остаётся служебным.
    rep = call("POST", f"/staff/objects/{oid}/publish", {"expected_revision": item["revision"],
               "reason": "Синтетическая причина: задержка поставки покрытия (проверка R09)"}, cookie, csrf)
    rec("r02_republish", rep["status"] == 200, rep["status"])
    a = ask("Почему перенесли срок?")
    rec("delay_reason_from_r02_public_history",
        "29.10.2026" in a["text"] and "задержка поставки покрытия" in a["text"] and "20.10.2026" in a["text"],
        a["text"][-300:])
    rec("staff_update_reason_not_public", "СЛУЖЕБНАЯ" not in a["text"], "")
    a = ask("Сколько стоит?")
    rec("unknown_budget_not_zero_r02", "нет данных" in a["text"] and " 0 ₸" not in a["text"], a["text"][:200])
    secret_probe = json.dumps(load(oid), ensure_ascii=False)
    rec("no_staff_fields_in_public_dto", not any(k in secret_probe for k in ("password", "csrf", "session", "internal")),
        "")

    # Редакторское извлечение с настоящим R02 resolve_principal (Principal-объект, а не dict).
    staff_ep = AssistantEndpoint(load, resolve_principal=svc.resolve_principal, rate_limiter=RateLimiter(100, 60))
    pub_text = json.loads((REPO / "tests/civic/R09/fixtures/publications.json").read_text(encoding="utf-8"))["ru_full"]
    body = {"source_id": pub_text["source_id"], "text": pub_text["text"]}

    def staff_ctx(with_cookie):
        headers = {"Host": "127.0.0.1:8501"}
        if with_cookie:
            headers.update({"Cookie": cookie, "X-CSRF-Token": csrf})
        return {"headers": headers, "client_ip": "127.0.0.1", "host_allowed": True, "is_same_origin": True,
                "is_https": False}

    ok_resp = staff_ep.handle("POST", "/staff/assistant/extract", {}, body, staff_ctx(True))
    anon = staff_ep.handle("POST", "/staff/assistant/extract", {}, body, staff_ctx(False))
    rec("extract_with_real_r02_principal", ok_resp["status"] == 200 and anon["status"] == 401
        and ok_resp["body"]["data"]["fields"]["schedule.current_planned_end"]["value"] == "2026-10-20",
        f"editor={ok_resp['status']} anonymous={anon['status']}")

    cases = [c["case_id"] for c in list_cases()]
    sid = "synthetic-tiny-v1-demo" if "synthetic-tiny-v1-demo" in cases else (cases[0] if cases else None)
    if sid:
        s = ask("Чем план A отличается от B?", object_id=None, scenario_id=sid)
        rec("scenario_from_real_r07_compare", s["intent"] == "scenario_compare" and "Пар с найденным путём" in s["text"]
            and not [w for w in s["warnings"] if w.startswith("audit")], s["text"][:300])
    else:
        rec("scenario_from_real_r07_compare", False, "no R07 cases")

    def sha(path):
        try:
            return subprocess.run(["git", "-C", path, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        except Exception:  # noqa: BLE001
            return None

    print(json.dumps({"r02_sha": sha(args.r02), "r07_sha": sha(args.r07), "r09_sha": sha(str(REPO)), "checks": checks},
                     ensure_ascii=False, indent=1))
    return 0 if all(c["status"] == "PASS" for c in checks) else 1


if __name__ == "__main__":
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    sys.exit(main())
