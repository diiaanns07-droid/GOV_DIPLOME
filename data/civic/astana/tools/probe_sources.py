"""Reachability probe for source URLs (R05). Records what happened; saves no page bodies.

* Uses urllib with the environment's proxy/CA settings; never disables TLS checks.
* At most --attempts tries per URL (default 2) with a pause; a policy 403 from the
  proxy is recorded and NOT retried around.
* Output: JSON list of {url, attempts:[{at, outcome, http_status, bytes, sha256, detail}]}.
  ``sha256`` is the hash of the received body, so a later fetch can be compared
  without committing the page itself.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "GOV_DIPLOME-R05-research/1.0 (thesis prototype; low-rate manual checks)"


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def probe(url: str, attempts: int = 2, timeout: float = 25.0, pause: float = 3.0,
          max_bytes: int = 5_000_000) -> dict:
    log = []
    for n in range(attempts):
        rec = {"at": _now(), "method": "python-urllib GET via environment proxy",
               "outcome": None, "http_status": None, "bytes": None, "sha256": None, "detail": None}
        try:
            safe_url = urllib.parse.quote(url, safe=":/?#[]@!$&'()*+,;=%~")
            req = urllib.request.Request(safe_url, headers={"User-Agent": UA, "Accept-Language": "ru,en;q=0.5"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read(max_bytes + 1)
                rec["http_status"] = resp.status
                rec["bytes"] = len(body)
                rec["sha256"] = hashlib.sha256(body).hexdigest()
                rec["final_url"] = resp.geturl()
                rec["content_type"] = resp.headers.get("Content-Type")
                rec["outcome"] = "fetched" if resp.status == 200 and len(body) <= max_bytes else "partial"
        except urllib.error.HTTPError as exc:
            rec["http_status"] = exc.code
            rec["outcome"] = "http_error"
            rec["detail"] = str(exc.reason)[:200]
        except (urllib.error.URLError, OSError) as exc:
            text = str(getattr(exc, "reason", exc))[:300]
            rec["outcome"] = "egress_denied" if "403" in text and "Tunnel" in text else "network_error"
            rec["detail"] = text
        except Exception as exc:  # malformed URL etc.: record, do not crash the batch
            rec["outcome"] = "client_error"
            rec["detail"] = f"{type(exc).__name__}: {exc}"[:300]
        log.append(rec)
        if rec["outcome"] in ("fetched", "http_error", "egress_denied"):
            break  # definitive answer; policy denials are not retried around
        if n + 1 < attempts:
            time.sleep(pause)
    return {"url": url, "attempts": log}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("urls", nargs="*")
    ap.add_argument("--from-file", help="text file with one URL per line")
    ap.add_argument("--attempts", type=int, default=2)
    ap.add_argument("--out", default="-")
    args = ap.parse_args(argv)
    urls = list(args.urls)
    if args.from_file:
        with open(args.from_file, encoding="utf-8") as fh:
            urls += [ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")]
    results = [probe(u, attempts=max(1, min(args.attempts, 3))) for u in urls]
    text = json.dumps(results, ensure_ascii=False, indent=2)
    if args.out == "-":
        print(text)
    else:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
