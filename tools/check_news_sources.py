"""Probe candidate news sources from the GitHub runner (the dev sandbox has no
access to these sites) and write a report: which RSS feeds and HTML news
listings work, how many items they give and how fresh they are.

Run: python tools/check_news_sources.py <out.json>
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "aggregator"))
import main as agg  # noqa: E402

RSS = {
    "sdelanounas": "https://sdelanounas.ru/index/rss/",
    "interfax": "https://www.interfax.ru/rss.asp",
    "tass": "https://tass.ru/rss/v2.xml",
    "kommersant-business": "https://www.kommersant.ru/RSS/section-business.xml",
    "rbc": "https://rssexport.rbc.ru/rbcnews/news/30/full.rss",
    "rg": "https://rg.ru/xml/index.xml",
    "kolesa": "https://www.kolesa.ru/rss",
    "5koleso": "https://5koleso.ru/rss/",
}

SITES = {
    "gruzovikpress": "https://gruzovikpress.ru/",
    "os1": "https://os1.ru/",
    "ati-news": "https://news.ati.su/",
    "tonar": "https://tonar.info/",
    "uralaz": "https://uralaz.ru/",
    "nefaz": "https://nefaz.ru/",
    "rostselmash": "https://rostselmash.com/",
    "kamaz": "https://kamaz.ru/",
    "gazgroup": "https://gazgroup.ru/",
    "chmzap": "https://chmzap.ru/",
    "maz": "https://maz.by/",
    "autostat": "https://www.autostat.ru/",
    "transportrussia": "https://transportrussia.ru/",
    "logirus": "https://logirus.ru/",
    "bez-ram": "https://www.polytrans.ru/",
    "grunwald": "https://grunwald.ru/",
}
LISTING_PATHS = ["news/", "press/", "press/news/", "press-center/news/", "media/news/", "novosti/", "company/news/",
                 "about/news/", "press-center/", "pressroom/", "articles/", "news/all/"]
KEYWORDS = ("грузов", "тягач", "полуприцеп", "прицеп", "спецтех", "самосвал", "камаз", "урал", "газ", "маз", "тонар",
            "автокран", "коммерческ", "автобус", "логист", "перевоз", "минтранс", "дорог")


def rss_check(url: str) -> dict:
    fp = agg.fetch_rss(url)
    entries = list(getattr(fp, "entries", []) or [])
    rows = []
    for e in entries[:60]:
        n = agg.normalize(e, "x", [])
        rows.append((n.get("published_at") or "", n.get("title") or "", n.get("summary") or ""))
    topical = [r for r in rows if any(k in (r[1] + " " + r[2]).lower() for k in KEYWORDS)]
    return {"items": len(entries), "latest": max((r[0] for r in rows), default=""), "topical": len(topical),
            "topical_titles": [r[1][:100] for r in topical[:6]]}


def find_feed_links(url: str) -> list[str]:
    try:
        r = agg.HTTP.get(url, timeout=(10, 20))
        html = r.text
    except Exception as exc:
        return [f"ERR {exc.__class__.__name__}"]
    return [urljoin(url, m) for m in re.findall(r'<link[^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]*href=["\']([^"\']+)', html, re.I)]


def listing_check(url: str) -> dict:
    src = {"url": url, "title": urlparse(url).netloc, "limit": 6}
    items = agg.fetch_html_news(src)
    return {"items": len(items), "dates": [i.get("published_at") for i in items],
            "titles": [i.get("title", "")[:100] for i in items]}


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "source_check.json")
    report = {"rss": {}, "sites": {}}
    for key, url in RSS.items():
        try:
            report["rss"][key] = {"url": url, **rss_check(url)}
        except Exception as exc:
            report["rss"][key] = {"url": url, "error": f"{exc.__class__.__name__}: {exc}"}
        print("rss", key, report["rss"][key].get("items"), report["rss"][key].get("topical"))
    for key, base in SITES.items():
        res = {"base": base, "feeds": find_feed_links(base), "listings": {}}
        for feed in res["feeds"][:3]:
            if feed.startswith("http"):
                try:
                    res.setdefault("feed_checks", {})[feed] = rss_check(feed)
                except Exception as exc:
                    res.setdefault("feed_checks", {})[feed] = {"error": str(exc)}
        for path in LISTING_PATHS:
            url = urljoin(base, path)
            try:
                r = agg.HTTP.get(url, timeout=(8, 15), allow_redirects=True)
                if r.status_code != 200 or len(r.text) < 2000:
                    continue
            except Exception:
                continue
            res["listings"][url] = listing_check(url)
            if res["listings"][url]["items"] >= 3:
                break
        report["sites"][key] = res
        print("site", key, res["feeds"][:2], {u: v["items"] for u, v in res["listings"].items()})
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
