"""Перенос результатов поискового workflow R05 в реестр источников и список кандидатов.

    python3 -I research/round-12-results/R05/import_search_results.py \
        research/round-12-results/R05/search/workflow_result.json \
        [--curation research/round-12-results/R05/search/curation.json]

Пишет data/civic/astana/round12-verified/sources.json и candidates.json. Ничего не «подтверждает»:
все источники остаются not_fetched (страницы не открывались — egress закрыт), а значения из выдачи
сохраняются как подсказки с происхождением (url / search_title / search_summary).
Детерминированно: одинаковый вход -> одинаковые байты.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parents[3]
PKG = REPO / "data/civic/astana/round12-verified"

PUBLISHERS = {
    "gov.kz": ("Акимат города Астаны (страница на портале gov.kz)", "official_gov"),
    "astana.gov.kz": ("Акимат города Астаны", "official_gov"),
    "inform.kz": ("МИА «Казинформ»", "state_media"),
    "kazinform.kz": ("МИА «Казинформ»", "state_media"),
    "kazpravda.kz": ("«Казахстанская правда»", "state_media"),
    "vechastana.kz": ("«Вечерняя Астана»", "city_media"),
    "astana-akshamy.kz": ("«Астана ақшамы»", "city_media"),
    "zakon.kz": ("Zakon.kz", "news"),
    "tengrinews.kz": ("Tengrinews.kz", "news"),
    "bes.media": ("Bes.media", "news"),
    "digitalbusiness.kz": ("Digital Business", "news"),
    "inbusiness.kz": ("Inbusiness.kz", "news"),
    "kursiv.media": ("Kursiv Media", "news"),
    "bizmedia.kz": ("Bizmedia.kz", "news"),
    "kapital.kz": ("Kapital.kz", "news"),
    "lsm.kz": ("LS", "news"),
    "finratings.kz": ("Finratings.kz", "news"),
    "astanatv.kz": ("Телеканал «Астана»", "city_media"),
}
URL_DATE = re.compile(r"/(20\d\d)-(\d\d)-(\d\d)(?:[/-]|$)")


def norm_url(url: str) -> str:
    url = url.strip().replace("http://", "https://", 1)
    url = re.sub(r"/amp/", "/", url)
    url = re.sub(r"/amp/?$", "/", url)
    parts = urlsplit(url)
    query = parts.query if "gov.kz" in parts.netloc else ""   # ?lang= на gov.kz различает версии страницы
    return f"https://{parts.netloc.lower()}{parts.path.rstrip('/') or '/'}" + (f"?{query}" if query else "")


def publisher_for(host: str):
    host = host.lower().removeprefix("www.").removeprefix("m.").removeprefix("kz.")
    for domain, value in PUBLISHERS.items():
        if host == domain or host.endswith("." + domain):
            return value
    return (None, "other")


def source_id(url: str) -> str:
    host = urlsplit(url).netloc.lower().removeprefix("www.")
    short = re.sub(r"[^a-z0-9]+", "-", host.split(".")[0])[:16]
    return f"src-r12-{short}-{hashlib.sha256(url.encode()).hexdigest()[:8]}"


def slug(text: str, limit: int = 40) -> str:
    table = str.maketrans({"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z",
                           "и": "i", "й": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
                           "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sh",
                           "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya", "ә": "a", "ғ": "g", "қ": "k",
                           "ң": "n", "ө": "o", "ұ": "u", "ү": "u", "һ": "h", "і": "i"})
    s = re.sub(r"[^a-z0-9]+", "-", text.lower().translate(table)).strip("-")
    return s[:limit].strip("-") or "item"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("result")
    ap.add_argument("--curation", default=None)
    args = ap.parse_args(argv)
    data = json.loads(Path(args.result).read_text(encoding="utf-8"))
    curation = json.loads(Path(args.curation).read_text(encoding="utf-8")) if args.curation else {}
    discovered_at = curation.get("discovered_at", "2026-10-07T10:16:00Z")

    sources, candidates, by_url = {}, [], {}
    ordered = sorted(data["candidates"], key=lambda c: norm_url(c["url"]))
    for cand in ordered:
        url = norm_url(cand["url"])
        sid = source_id(url)
        host = urlsplit(url).netloc
        publisher, kind = publisher_for(host)
        m = URL_DATE.search(urlsplit(url).path)
        sources[sid] = {
            "id": sid, "url": url, "publisher": publisher, "publisher_kind": kind if publisher else cand.get("source_kind", "other"),
            "title_as_listed": cand["title_as_listed"],
            "published_on": "-".join(m.groups()) if m else None, "published_on_basis": "url" if m else None,
            "discovered_via": {"tool": "WebSearch (server-side)", "at": discovered_at,
                               "query": f"workflow sweep: {cand.get('sweep')}"},
            "access_status": "not_fetched", "retrieved_at": None, "content_sha256": None, "fetch_method": None,
            "license": None,
            "license_status": "unknown",
            "access_attempts": [{"at": discovered_at, "method": "WebSearch result (no page fetch)",
                                 "outcome": "listed_in_search",
                                 "detail": "страница не открыта: egress закрыт (network_audit.json)"}],
        }
        by_url[url] = sid

    seen_ids = set()
    for cand in ordered:
        url = norm_url(cand["url"])
        verdict = cand.get("verdict") or {}
        decision = {"keep": "to_verify", "reject": "rejected", "duplicate": "duplicate"}.get(verdict.get("decision"), "to_verify")
        cur = curation.get("overrides", {}).get(url, {})
        decision = cur.get("decision", decision)
        cid = f"cand-r12-{slug(cand['title_as_listed'], 34)}"
        base, n = cid, 2
        while cid in seen_ids:
            cid, n = f"{base}-{n}", n + 1
        seen_ids.add(cid)
        corroborating = [norm_url(u) for u in verdict.get("corroborating_urls") or [] if norm_url(u) in by_url]
        date_hint = verdict.get("best_date_hint") or cand.get("date_hint") or ""
        origin = verdict.get("best_date_origin") or cand.get("date_hint_origin") or "none"
        if origin not in ("url", "search_title", "search_summary", "none"):
            origin = "none"
        hints = [{"field": h["field"], "text": h["value_text"], "origin": h["origin"]} for h in cand.get("claims") or []]
        candidates.append({
            "id": cid, "decision": decision,
            "reason": cur.get("reason") or verdict.get("reason") or "не проверено скептиком (оставлено к проверке)",
            "kind": cur.get("kind", cand["kind"]),
            "title_as_listed": cand["title_as_listed"],
            "source_ids": [by_url[url]] + [by_url[u] for u in corroborating if by_url[u] != by_url[url]],
            "duplicate_of_url": norm_url(verdict["duplicate_of_url"]) if verdict.get("duplicate_of_url") else None,
            "location_text": cand.get("location_text") or "",
            "date_hint": date_hint, "date_hint_origin": origin,
            "freshness": verdict.get("freshness", "unknown"),
            "city_check": verdict.get("city_check", "unclear"),
            "contradictions": verdict.get("contradictions") or "",
            "hints": hints,
            "verify_checklist": cur.get("checklist") or [
                "открыть URL; убедиться, что речь об Астане и указана дата публикации",
                "выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт",
                "сумму и основание (план/договор/освоено) — только если названы на странице",
                "отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)",
            ],
            "geocode": cur.get("geocode"),
            "found_by_sweeps": sorted({cand.get("sweep")} | set(cand.get("also_found_by") or [])),
        })
    # duplicate_of_url -> id кандидата
    url_to_cid = {}
    for cand, rec in zip(ordered, candidates):
        url_to_cid.setdefault(norm_url(cand["url"]), rec["id"])
    for rec in candidates:
        dup_url = rec.pop("duplicate_of_url")
        rec["duplicate_of"] = url_to_cid.get(dup_url) if dup_url else None
        if rec["decision"] == "duplicate" and not rec["duplicate_of"]:
            rec["decision"], rec["reason"] = "to_verify", rec["reason"] + " (дубликат указан на URL вне списка — оставлено к проверке)"

    (PKG / "sources.json").write_text(json.dumps(
        {"schema": "r05-r12-sources-v1", "city": "astana", "registry_as_of": curation.get("as_of", "2026-10-07"),
         "note": "Все источники найдены серверным поиском; ни одна страница в среде R05 не открыта (network_audit.json). "
                 "published_on заполнен только там, где дата есть в самом URL (published_on_basis=url).",
         "sources": [sources[k] for k in sorted(sources)]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (PKG / "candidates.json").write_text(json.dumps(
        {"schema": "r05-r12-candidates-v1", "city": "astana", "as_of": curation.get("as_of", "2026-10-07"),
         "note": "Кандидаты НЕ подтверждены: найдены поиском, страницы не открывались. Не импортируются. "
                 "hints с origin=search_summary — пересказ поисковой модели, самый ненадёжный уровень.",
         "queries": data.get("queries", []),
         "candidates": candidates}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"sources": len(sources), "candidates": len(candidates),
                      "by_decision": {d: sum(1 for c in candidates if c["decision"] == d) for d in ("to_verify", "rejected", "duplicate")}},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
