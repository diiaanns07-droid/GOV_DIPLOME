"""Нагрузочный прогон R02 через настоящий HTTP (не pytest): python tests/civic/R06/store/r06store_stress_http.py [секунды].

Временная база во временной папке; результаты для PERF.txt. Пароли — только для этой временной базы.
"""
import collections
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from ui.civic_store.http_adapter import CivicHttpAdapter, make_reference_handler  # noqa: E402
from ui.civic_store.service import CivicService  # noqa: E402

DURATION = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
DB = str(Path(tempfile.mkdtemp(prefix="civic-stress-")) / "stress.sqlite3")
svc = CivicService(DB)
for i in range(4):
    svc.accounts.create_user(f"stress{i}", f"Stress-Strong-Pass-{i}9")
server = ThreadingHTTPServer(("127.0.0.1", 0), make_reference_handler(CivicHttpAdapter(svc)))
server.daemon_threads = True
port = server.server_address[1]
threading.Thread(target=server.serve_forever, daemon=True).start()
codes = collections.Counter(); lock = threading.Lock(); lat = []

def req(method, path, body=None, cookie=None, csrf=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    h = {"Host": f"127.0.0.1:{port}"}
    if method == "POST":
        h["Origin"] = f"http://127.0.0.1:{port}"; h["Content-Type"] = "application/json"
    if cookie: h["Cookie"] = f"civic_session={cookie}"
    if csrf: h["X-CSRF-Token"] = csrf
    t = time.time()
    c.request(method, "/api/civic/v1" + path, body=json.dumps(body).encode() if body is not None else None, headers=h)
    r = c.getresponse(); data = r.read(); c.close()
    with lock:
        codes[(method, path.split("/")[1] if "/" in path else path, r.status)] += 1; lat.append(time.time() - t)
    return r.status, dict(r.getheaders()), json.loads(data) if data else None

def login(i):
    s, h, b = req("POST", "/session/login", {"username": f"stress{i}", "password": f"Stress-Strong-Pass-{i}9"})
    return h["Set-Cookie"].split(";")[0].split("=", 1)[1], b["data"]["csrf_token"]

END = time.time() + DURATION
def writer(i):
    cookie, csrf = login(i % 4)
    while time.time() < END:
        s, _, b = req("POST", "/staff/objects", {"kind": "event", "title": f"S{i}", "evidence_type": "synthetic",
                       "schedule": {"planned_start": "2026-10-10", "original_planned_end": None, "current_planned_end": "2026-10-20", "actual_end": None}}, cookie, csrf)
        if s != 201: continue
        item = b["data"]["item"]
        s, _, b = req("POST", f"/staff/objects/{item['id']}/publish", {"expected_revision": 1, "reason": "stress"}, cookie, csrf)
        if s == 200:
            item = b["data"]["item"]
            req("POST", f"/staff/objects/{item['id']}/update", {"expected_revision": item["revision"], "reason": "r",
                "changes": {"schedule": {"current_planned_end": "2026-10-25"}}}, cookie, csrf)
def reader(i):
    while time.time() < END:
        s, _, b = req("GET", "/objects?limit=20")
        if s == 200 and b["data"]["items"]:
            req("GET", f"/objects/{b['data']['items'][0]['id']}")
def loginer(i):
    while time.time() < END:
        req("POST", "/session/login", {"username": f"stress{i % 4}", "password": f"Stress-Strong-Pass-{i % 4}9"})

threads = [threading.Thread(target=writer, args=(i,)) for i in range(8)] + \
          [threading.Thread(target=reader, args=(i,)) for i in range(6)] + \
          [threading.Thread(target=loginer, args=(i,)) for i in range(2)]
t0 = time.time()
for t in threads: t.start()
for t in threads: t.join()
server.shutdown()
total = sum(codes.values())
print("requests", total, "in", round(time.time() - t0, 1), "s;", round(total / (time.time() - t0)), "req/s")
for k, v in sorted(codes.items()): print(k, v)
lat.sort(); print("p50 ms", round(lat[len(lat)//2]*1000, 1), "p99 ms", round(lat[int(len(lat)*0.99)]*1000, 1), "max ms", round(lat[-1]*1000, 1))
print("open connections", svc.db.open_connections)
with svc.db.read() as conn:
    print("objects", conn.execute("select count(*) from civic_objects").fetchone()[0],
          "public", conn.execute("select count(*) from civic_public_objects").fetchone()[0],
          "history", conn.execute("select count(*) from civic_history").fetchone()[0])
    bad = conn.execute("""select count(*) from civic_objects o where revision != (select max(revision) from civic_history h where h.object_id=o.id)""").fetchone()[0]
    print("objects whose revision != last history revision:", bad)
    bad2 = conn.execute("""select count(*) from civic_objects o where (publication='published') != exists(select 1 from civic_public_objects p where p.id=o.id)""").fetchone()[0]
    print("publication/projection mismatches:", bad2)
