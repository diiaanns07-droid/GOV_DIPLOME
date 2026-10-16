"""HTTP-проверка «ИИ-разбора пачки» (П3) на стенде: шлюз R01 с маршрутами intake/analyze, intake/sample, intake/commit.

Не pytest (нужен запущенный сервер с маршрутами — research/round-15-results/R04/patches/r01_intake_routes.patch или
сборка R01). Запуск:
    R04_STAND=http://127.0.0.1:8655 python3 -B tests/civic/R04/intake/http_check_intake.py
Пароль редактора — R04_STAND_PASSWORD (по умолчанию parol-r04-test, как в RUN.txt). Без внешней сети.
"""
import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("R04_STAND", "http://127.0.0.1:8655")
V2 = BASE + "/api/civic/v2"
PII = ("87011234567", "880101300123")
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
results = []


def call(method, path, body=None, headers=None, raw=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request((V2 if path.startswith("/") and not path.startswith("/api") else BASE) + path,
                                 data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Origin", BASE)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    t0 = time.perf_counter()
    try:
        with opener.open(req, timeout=60) as resp:
            status, payload = resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        status, payload = exc.code, exc.read()
    except (urllib.error.URLError, ConnectionError) as exc:   # сервер закрыл соединение, не дочитав тело (> 2 × предела)
        status, payload = 0, json.dumps({"error": "connection_closed", "message": str(exc)}).encode()
    try:
        out = json.loads(payload or b"{}")
    except ValueError:
        out = {"raw": payload[:200].decode("utf-8", "replace")}
    if isinstance(out, dict) and out.get("ok") is True and "data" in out:
        out = out["data"]
    return status, out, round((time.perf_counter() - t0) * 1000, 1)


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {str(detail)[:400]}"))


st, body, _ = call("GET", "/modules")
mods = body.get("modules", {}) if isinstance(body, dict) else {}
check("modules: ml.intake_* ready", all(mods.get(k, {}).get("status") == "ready"
                                        for k in ("ml.intake_analyze", "ml.intake_sample", "ml.intake_commit")),
      {k: mods.get(k) for k in ("ml.intake_analyze", "ml.intake_sample", "ml.intake_commit")})

st, body, _ = call("POST", "/intake/analyze", {"sample": "night"})
check("analyze without staff -> 401/403", st in (401, 403), (st, body))
st, body, _ = call("GET", "/intake/sample")
check("sample without staff -> 401/403", st in (401, 403), (st, body))

st, body, _ = call("POST", "/api/civic/v1/session/login",
                   {"username": "operator", "password": os.environ.get("R04_STAND_PASSWORD", "parol-r04-test")})
csrf = (body.get("data") or {}).get("csrf_token") if isinstance(body.get("data"), dict) else body.get("csrf_token")
check("staff login", st == 200 and csrf, (st, body))
H = {"X-CSRF-Token": csrf or ""}

st, body, _ = call("POST", "/intake/analyze", {"sample": "night"})
check("analyze without CSRF -> 403", st == 403, (st, body))

st, sample, ms = call("GET", "/intake/sample", None, H)
check("sample -> 200 demo", st == 200 and sample.get("demo") is True and len(sample.get("texts") or []) >= 30, (st, sample))
print("   sample:", len(sample.get("texts") or []), "texts,", sample.get("source"), "|", ms, "ms")

st, res, ms = call("POST", "/intake/analyze", {"sample": "night"}, H)
s = res.get("summary") or {}
tasks = res.get("tasks") or []
check("analyze sample -> 200, numbers from tasks", st == 200 and res.get("demo") is True and s.get("tasks") == len(tasks)
      and s.get("total") == sum(t["people"] for t in tasks) and s.get("merged") == s.get("total", 0) - s.get("tasks", 0)
      and s.get("ready") == sum(1 for t in tasks if t.get("target")), (st, s))
check("no PII in analyze response", not any(p in json.dumps(res, ensure_ascii=False) for p in PII))
print("   summary:", json.dumps(s, ensure_ascii=False), "| http", ms, "ms")

texts = [t["text"] for t in sample.get("texts") or []]
batch = [texts[i % len(texts)] + f" ({i // len(texts) + 1})" for i in range(300)]
st, big, ms = call("POST", "/intake/analyze", {"texts": batch}, H)
check("analyze 300 texts -> 200 within 10 s", st == 200 and big["summary"]["total"] == 300 and ms < 10_000, (st, ms))
print("   300 texts:", json.dumps(big.get("summary"), ensure_ascii=False), "| http", ms, "ms")

st, body, _ = call("POST", "/intake/analyze", {"texts": []}, H)
check("analyze empty -> 400", st == 400, (st, body))
st, body, _ = call("POST", "/intake/analyze", {"texts": ["Яма на дороге"] * 501}, H)
check("analyze 501 texts -> 400", st == 400, (st, body))
st, body, _ = call("POST", "/intake/analyze", None, H, raw=json.dumps({"texts": ["я" * 1990] * 90}).encode())
check("analyze > 300 KB -> 400/413", st in (400, 413), (st, body))
st, body, _ = call("POST", "/intake/analyze", None, H, raw=json.dumps({"texts": ["я" * 1990] * 200}).encode())
check("analyze body > 640 KB -> 413 or closed", st in (413, 0), (st, body))

# ready = новые записи (created; если пачку уже создавали — existing) + задачи к уже открытым обращениям цели.
st, done, ms = call("POST", "/intake/commit", {"batch_id": res.get("batch_id")}, H)
handled = done.get("created", 0) + done.get("existing", 0) + done.get("joined_existing", 0)
check("commit -> 200, created + existing + joined_existing == ready", st == 200 and handled == s.get("ready")
      and done.get("failed") == 0 and done.get("skipped_no_address") == s.get("no_address"),
      (st, {k: v for k, v in done.items() if k != "records"}))
print("   commit:", json.dumps({k: v for k, v in done.items() if k != "records"}, ensure_ascii=False), "|", ms, "ms")
st, again, _ = call("POST", "/intake/commit", {"batch_id": res.get("batch_id")}, H)
check("commit again -> no duplicates", st == 200 and again.get("created") == 0 and again.get("joined") == 0
      and again.get("existing", 0) + again.get("joined_existing", 0) == s.get("ready"),
      (st, {k: v for k, v in again.items() if k != "records"}))
rec = next((r for r in done.get("records") or [] if r.get("complaint_id")), None)
if rec:
    st, one, _ = call("GET", "/complaints/" + rec["complaint_id"], None, H)
    item = one.get("item") or one.get("complaint") or one
    check("created record is in R09, demo", st == 200 and item.get("demo") is True, (st, str(one)[:300]))
    check("no PII in created record", not any(p in json.dumps(one, ensure_ascii=False) for p in PII))
st, body, _ = call("POST", "/intake/commit", {"batch_id": "f" * 16}, H)
check("commit unknown batch -> 404", st == 404, (st, body))
st, body, _ = call("POST", "/intake/commit", {"batch_id": "../x"}, H)
check("commit bad batch -> 400", st == 400, (st, body))

print("SUMMARY", sum(ok for _, ok in results), "/", len(results))
sys.exit(0 if all(ok for _, ok in results) else 1)
