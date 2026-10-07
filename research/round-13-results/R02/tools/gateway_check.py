"""Проверка маршрутов R02 через настоящий шлюз ui/web_server.py (после patch из INTEGRATION.txt).

python3 gateway_check.py BASE_URL DB_PATH PASSWORD_FILE USERNAME  (из корня проверяемой сборки)
Импорт выполняется CLI на той же временной БД; содержимое тестовое (example.org).
Печатает JSON-журнал шагов без cookie/CSRF/пароля.
"""

import http.cookiejar
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

BASE, DB, PWFILE, USER = sys.argv[1:5]
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
csrf = None
log = []


def req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Origin": BASE, "Content-Type": "application/json"}
    if csrf:
        headers["X-CSRF-Token"] = csrf
    r = urllib.request.Request(BASE + "/api/civic/v1" + path, data=data, method=method, headers=headers)
    try:
        with opener.open(r) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def step(name, status, body, expect):
    ok = status == expect
    log.append({"step": name, "status": status, "expected": expect, "ok": ok,
                "code": (body.get("error") or {}).get("code")})
    return body


def item(version, end):
    return {"schema_version": "civic-v1", "city": "astana",
            "slice": {"name": "r02-gateway-check", "version": version, "demo": False, "source": "r02-gateway-check"},
            "items": [{"id": "r02-gw-1", "kind": "roadworks", "title": "ТЕСТ шлюза (не реальная работа)",
                       "status": "planned", "evidence_type": "hypothesis",
                       "schedule": {"planned_start": "2026-10-14", "original_planned_end": None,
                                    "current_planned_end": end, "actual_end": None},
                       "source_refs": [{"id": "src-1", "url": "https://example.org/gw", "publisher": "ТЕСТ",
                                        "published_on": "2026-10-01", "retrieved_at": None,
                                        "access_status": "not_fetched", "license": None,
                                        "fields": ["schedule.current_planned_end"]}]}]}


def cli_import(pkg):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(pkg, f, ensure_ascii=False)
    out = subprocess.run([sys.executable, "-m", "ui.civic_store", "--db", DB, "import", f.name],
                         capture_output=True, text=True, check=True)
    Path(f.name).unlink()
    return json.loads(out.stdout)


step("meta без входа", *req("GET", "/staff/meta"), 401)
s, b = req("POST", "/session/login", {"username": USER, "password": Path(PWFILE).read_text().strip()})
step("вход", s, b, 200)
csrf = b["data"]["csrf_token"]
meta = step("meta", *req("GET", "/staff/meta"), 200)
log.append({"meta_version": meta["data"]["meta_version"]})
step("audit", *req("GET", "/staff/audit"), 200)
cli_import(item("v1", "2026-10-20"))
obj = step("карточка", *req("GET", "/staff/objects/r02-gw-1"), 200)["data"]["item"]
obj = step("публикация", *req("POST", "/staff/objects/r02-gw-1/publish",
                                {"expected_revision": obj["revision"], "reason": "Публикация"}), 200)["data"]["item"]
report = cli_import(item("v2", "2026-11-30"))
log.append({"import_v2_action": report["items"][0]["action"]})
cands = step("кандидаты", *req("GET", "/staff/objects/r02-gw-1/import-candidates"), 200)["data"]["items"]
cid = cands[0]["id"]
step("apply со старой ревизией", *req("POST", f"/staff/objects/r02-gw-1/import-candidates/{cid}/apply",
                                       {"expected_revision": obj["revision"] - 1, "reason": "x"}), 409)
res = step("apply", *req("POST", f"/staff/objects/r02-gw-1/import-candidates/{cid}/apply",
                          {"expected_revision": obj["revision"], "reason": "Срок по источнику"}), 200)
rev = res["data"]["item"]["revision"]
step("dismiss уже решённого", *req("POST", f"/staff/objects/r02-gw-1/import-candidates/{cid}/dismiss",
                                    {"expected_revision": rev, "reason": "x"}), 409)
step("неизвестный маршрут кандидата", *req("POST", f"/staff/objects/r02-gw-1/import-candidates/{cid}/delete",
                                            {}), 404)
pub = step("публичная карточка", *req("GET", "/objects/r02-gw-1"), 200)["data"]["item"]
log.append({"public_current_end_before_publish": pub["schedule"]["current_planned_end"]})
print(json.dumps({"base": BASE, "all_ok": all(e.get("ok", True) for e in log), "steps": log},
                 ensure_ascii=False, indent=1))
