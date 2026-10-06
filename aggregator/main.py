# aggregator/main.py
from __future__ import annotations
import json, sys, time, re
import html as html_lib
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import requests, feedparser, yaml  # pip install requests feedparser pyyaml

VER = "safe-collector v2.1"

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "frontend" / "data"
NEWS_JSON = DATA_DIR / "news.json"
META_JSON = DATA_DIR / "news_meta.json"
CFG_PATH = ROOT / "aggregator" / "sources.yml"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")
HTTP = requests.Session()
HTTP.headers.update({"User-Agent": UA, "Accept": "*/*"})

def log(k: str, msg: str) -> None:
    print(f"[{k}] {msg}")

def load_cfg() -> Dict[str, Any]:
    with CFG_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def fetch_rss(url: str):
    try:
        r = HTTP.get(url, timeout=(10, 20))
        r.raise_for_status()
        return feedparser.parse(r.content)
    except Exception as e:
        log("ERR", f"fetch {url}: {e.__class__.__name__}: {e}")
        return None

def to_iso(dt_struct) -> Optional[str]:
    if not dt_struct:
        return None
    try:
        ts = time.mktime(dt_struct)
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except Exception:
        return None

def image_from_html(value: str) -> Optional[str]:
    """Extract the first usable image URL from RSS HTML."""
    if not value:
        return None
    match = re.search(
        r'<img[^>]+(?:src|data-src|data-lazy-src)=["\']([^"\']+)["\']',
        str(value),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    url = html_lib.unescape(match.group(1)).strip()
    return url if url.startswith(("http://", "https://")) else None


def page_meta_image(url: str) -> Optional[str]:
    """Best-effort og:image/twitter:image lookup for feeds that omit media."""
    if not url or not url.startswith(("http://", "https://")):
        return None
    try:
        r = HTTP.get(url, timeout=(5, 8), allow_redirects=True)
        r.raise_for_status()
        content_type = str(r.headers.get("Content-Type", ""))
        if "html" not in content_type.lower():
            return None
        page = r.text[:350_000]
        patterns = [
            r'<meta[^>]+property=["\']og:image(?::secure_url)?["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image(?::secure_url)?["\']',
            r'<meta[^>]+name=["\']twitter:image(?::src)?["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image(?::src)?["\']',
        ]
        for pattern in patterns:
            match = re.search(pattern, page, flags=re.IGNORECASE)
            if match:
                image = html_lib.unescape(match.group(1)).strip()
                if image.startswith(("http://", "https://")):
                    return image
    except Exception:
        return None
    return None


def first_image(entry) -> Optional[str]:
    media = entry.get("media_content")
    if isinstance(media, list) and media:
        url = media[0].get("url")
        if url: return url
    for link in entry.get("links", []) or []:
        if link.get("rel") == "enclosure" and str(link.get("type","")).startswith(("image/","img/")):
            if link.get("href"): return link["href"]
    thumbs = entry.get("media_thumbnail")
    if isinstance(thumbs, list) and thumbs:
        url = thumbs[0].get("url")
        if url: return url
    if entry.get("image") and isinstance(entry["image"], dict):
        if entry["image"].get("href"): return entry["image"]["href"]

    # Some RSS feeds embed the only image inside summary/content HTML.
    candidates = [entry.get("summary") or ""]
    for block in entry.get("content") or []:
        if isinstance(block, dict):
            candidates.append(block.get("value") or "")
    for candidate in candidates:
        image = image_from_html(candidate)
        if image:
            return image
    return None

def clean_summary(value: str) -> str:
    """Convert RSS HTML summaries into compact plain text for cards/search."""
    if not value:
        return ""
    text = str(value)
    text = re.sub(r"<\s*br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</\s*(p|div|li|h[1-6])\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<\s*(figure|figcaption)[^>]*>.*?</\s*\1\s*>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<\s*(img|script|style|iframe)[^>]*>.*?</\s*\1\s*>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<\s*img[^>]*?/?>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def _meta_content(soup: BeautifulSoup, attr: str, value: str) -> str:
    tag = soup.find("meta", attrs={attr: value})
    return str(tag.get("content") or "").strip() if tag else ""


def _html_date(soup: BeautifulSoup) -> Optional[str]:
    candidates = [
        _meta_content(soup, "property", "article:published_time"),
        _meta_content(soup, "name", "date"),
    ]
    time_tag = soup.find("time")
    if time_tag:
        candidates.append(str(time_tag.get("datetime") or time_tag.get_text(" ", strip=True)))
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            payload = json.loads(script.string or "")
            nodes = payload if isinstance(payload, list) else [payload]
            for node in nodes:
                if isinstance(node, dict) and node.get("datePublished"):
                    candidates.append(str(node["datePublished"]))
        except Exception:
            pass
    for value in candidates:
        if not value:
            continue
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.astimezone(timezone.utc).isoformat()
        except Exception:
            match = re.search(r"(20\d{2})[-./](\d{1,2})[-./](\d{1,2})", value)
            if match:
                try:
                    dt = datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), tzinfo=timezone.utc)
                    return dt.isoformat()
                except Exception:
                    pass
    return _text_date(soup)


RU_MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}


def _text_date(soup: BeautifulSoup) -> Optional[str]:
    """Fallback for manufacturer sites without date metadata: the first
    «30.09.2026» or «30 сентября 2026» in the article area (not in the page
    footer, where copyright years live)."""
    node = None
    for selector in ("article", ".news-detail", ".detail_text", ".news", ".content", "main"):
        node = soup.select_one(selector)
        if node:
            break
    text = " ".join((node or soup).stripped_strings)[:4000]
    now = datetime.now(timezone.utc)
    found = []
    for d, mth, y in re.findall(r"\b(\d{1,2})\.(\d{1,2})\.(20\d{2})\b", text):
        found.append((int(y), int(mth), int(d)))
    for d, word, y in re.findall(r"\b(\d{1,2})\s+(" + "|".join(RU_MONTHS) + r")\s+(20\d{2})", text.lower()):
        found.append((int(y), RU_MONTHS[word], int(d)))
    for y, mth, d in found:
        try:
            dt = datetime(y, mth, d, 9, 0, tzinfo=timezone.utc)
        except ValueError:
            continue
        if dt <= now:
            return dt.isoformat()
    return None


def _detail_summary(soup: BeautifulSoup, title: str, limit: int = 900) -> str:
    for selector in ("article", ".news-detail", ".detail_text", ".detail-text", ".content", "main"):
        node = soup.select_one(selector)
        if not node:
            continue
        for junk in node.select("script,style,nav,footer,form,button,.breadcrumb,.breadcrumbs"):
            junk.decompose()
        text = " ".join(node.stripped_strings)
        text = re.sub(r"\s+", " ", text).strip()
        if title and text.lower().startswith(title.lower()):
            text = text[len(title):].lstrip(" .:-")
        if len(text) >= 80:
            if len(text) > limit:
                cut = text[:limit].rsplit(" ", 1)[0].rstrip(" ,.;:-")
                text = (cut or text[:limit]).rstrip() + "…"
            return text
    return ""


def _detail_image(soup: BeautifulSoup, page_url: str) -> Optional[str]:
    for attr, name in (("property", "og:image"), ("name", "twitter:image")):
        value = _meta_content(soup, attr, name)
        if value:
            return urljoin(page_url, value)
    for selector in ("article img", ".news-detail img", ".detail_text img", ".content img", "main img"):
        img = soup.select_one(selector)
        if img:
            src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
            if src:
                return urljoin(page_url, str(src))
    return None


def fetch_html_news(src: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Collect a public HTML news listing without copying full article text."""
    index_url = str(src.get("url") or "").strip()
    name = str(src.get("title") or src.get("name") or "source").strip()
    tags = [str(tag) for tag in (src.get("tags") or []) if tag]
    limit = max(1, min(int(src.get("limit") or 20), 50))
    seed_urls = [str(url).strip() for url in (src.get("seed_urls") or []) if url]

    urls: List[str] = []
    try:
        r = HTTP.get(index_url, timeout=(10, 20), allow_redirects=True)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        base_host = urlparse(index_url).netloc
        base_path = urlparse(index_url).path.rstrip("/")
        for a in soup.find_all("a", href=True):
            absolute = urljoin(index_url, str(a.get("href") or ""))
            parsed = urlparse(absolute)
            path = parsed.path.rstrip("/")
            if parsed.netloc != base_host:
                continue
            if not path.startswith(base_path + "/") or path == base_path:
                continue
            if absolute not in urls:
                urls.append(absolute)
    except Exception as exc:
        log("ERR", f"{name}: html listing: {exc.__class__.__name__}: {exc}")

    for seed in seed_urls:
        if seed not in urls:
            urls.append(seed)

    items: List[Dict[str, Any]] = []
    for page_url in urls[:limit]:
        try:
            r = HTTP.get(page_url, timeout=(8, 15), allow_redirects=True)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "lxml")
            title_node = soup.find("h1")
            title = clean_summary(title_node.get_text(" ", strip=True) if title_node else "")
            if not title:
                title = clean_summary(_meta_content(soup, "property", "og:title"))
            if not title:
                continue

            summary = clean_summary(_meta_content(soup, "name", "description")) or _detail_summary(soup, title)
            image = _detail_image(soup, page_url)
            items.append({
                "source": name,
                "title": title,
                "link": page_url,
                "summary": summary,
                "content": "",
                "image": image,
                "published_at": _html_date(soup),
                "domain": urlparse(page_url).netloc,
                "tags": tags,
                "partner": bool(src.get("partner")),
            })
        except Exception as exc:
            log("ERR", f"{name}: detail {page_url}: {exc.__class__.__name__}: {exc}")

    log("OK", f"{name}: +{len(items)} html-news")
    return items


def normalize(entry, src_name: str, src_tags: Optional[List[str]] = None) -> Dict[str, Any]:
    title = (entry.get("title") or "").strip() or "(без заголовка)"
    link = entry.get("link") or ""
    summary_raw = (entry.get("summary") or "").strip()
    contents = entry.get("content") or []
    content_raw = ""
    if isinstance(contents, list) and contents:
        content_raw = "\n\n".join(
            str(block.get("value") or "").strip()
            for block in contents
            if isinstance(block, dict) and block.get("value")
        ).strip()
    if not summary_raw and content_raw:
        summary_raw = content_raw

    summary = clean_summary(summary_raw)
    content = clean_summary(content_raw)
    if content and len(content) <= len(summary) + 120:
        content = ""
    published = to_iso(entry.get("published_parsed")) or to_iso(entry.get("updated_parsed"))
    img = first_image(entry)
    if not img:
        img = page_meta_image(link)
    domain = ""
    try:
        from urllib.parse import urlparse
        domain = urlparse(link).netloc
    except Exception:
        pass
    return {
        "source": src_name,
        "title": title,
        "link": link,
        "summary": summary,
        "content": content,
        "image": img,
        "published_at": published,
        "domain": domain,
        "tags": list(src_tags or []),
    }

def collect(sources_cfg: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for src in sources_cfg or []:
        if src.get("enabled") is False:
            continue
        name = src.get("title") or src.get("name") or "source"
        url = src.get("url") or src.get("link") or ""
        if not url:
            log("ERR", f"{name}: empty url")
            continue
        kind = str(src.get("kind") or "rss").lower()
        if kind == "html_news":
            items.extend(fetch_html_news(src))
            continue
        fp = fetch_rss(url)
        entries = []
        if fp and getattr(fp, "entries", None):
            entries = list(fp.entries)  # гарантированно список
        else:
            log("ERR", f"{name}: entries empty")
        got = 0
        # General-industry feeds: keep only items about commercial vehicles.
        include = [str(k).lower() for k in (src.get("include_keywords") or []) if k]
        for e in entries:
            try:
                item = normalize(e, name, src.get("tags") or [])
                if include and not any(k in (item["title"] + " " + item["summary"]).lower() for k in include):
                    continue
                items.append(item)
                got += 1
            except Exception as ex:
                log("ERR", f"{name}: normalize error: {ex}")
        log("OK", f"{name}: +{got}")
    return items

def read_existing() -> List[Dict[str, Any]]:
    try:
        if NEWS_JSON.exists():
            return json.loads(NEWS_JSON.read_text("utf-8"))
    except Exception:
        pass
    return []

def item_key(it: Dict[str, Any]) -> str:
    return str(
        it.get("canonical_url")
        or it.get("url")
        or it.get("link")
        or it.get("guid")
        or it.get("title")
        or ""
    ).strip()


def _looks_russian(value: Any) -> bool:
    return bool(value and re.search(r"[А-Яа-яЁё]", str(value)))


def preserve_stable_identity(fresh: List[Dict[str, Any]], existing: List[Dict[str, Any]]) -> None:
    """Carry persistent identity and completed translations onto refreshed items.

    RSS feeds return the source-language title/summary on every run. Without
    preserving the already translated Russian fields, the translation stage
    would redo the same archive on every ingest.
    """
    previous = {item_key(it): it for it in existing if item_key(it)}
    for it in fresh:
        old = previous.get(item_key(it))
        if not old:
            continue

        for field in ("id", "slug", "content", "image", "published_at", "tags", "partner"):
            if old.get(field) and not it.get(field):
                it[field] = old[field]

        # Normal incremental path: translator marks completed items.
        if old.get("translation_status") == "ru":
            for field in (
                "title",
                "summary",
                "translation_status",
                "translation_source_lang",
                "translation_updated_at",
                "original_title",
                "original_summary",
            ):
                if field in old:
                    it[field] = old[field]
            continue

        # One-time migration for legacy translated rows created before
        # translation metadata existed. A Russian stored title replacing a
        # fresh non-Russian source title is strong evidence of prior translation.
        old_title = str(old.get("title") or "")
        fresh_title = str(it.get("title") or "")
        if _looks_russian(old_title) and fresh_title and not _looks_russian(fresh_title):
            it["original_title"] = fresh_title
            it["title"] = old_title
            fresh_summary = str(it.get("summary") or "")
            old_summary = str(old.get("summary") or "")
            if _looks_russian(old_summary):
                it["original_summary"] = fresh_summary
                it["summary"] = old_summary
            it["translation_status"] = "ru"
            if old.get("translation_source_lang"):
                it["translation_source_lang"] = old["translation_source_lang"]
            if old.get("translation_updated_at"):
                it["translation_updated_at"] = old["translation_updated_at"]


def dedup_by_link(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen, out = set(), []
    for it in items:
        key = item_key(it)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out

def sort_by_date(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def key(it):
        val = it.get("published_at")
        try:
            return datetime.fromisoformat(val.replace("Z","+00:00")) if val else datetime.min.replace(tzinfo=timezone.utc)
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)
    return sorted(items, key=key, reverse=True)

def save(items: List[Dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    NEWS_JSON.write_text(json.dumps(items, ensure_ascii=False, indent=2), "utf-8")
    META_JSON.write_text(
        json.dumps({"updated_at": datetime.now(timezone.utc).isoformat(), "count": len(items)}, ensure_ascii=False, indent=2),
        "utf-8",
    )

def stats(items: List[Dict[str, Any]]) -> None:
    from collections import Counter
    c = Counter(it.get("domain") for it in items if it.get("domain"))
    if not c:
        log("STATS", "total: 0")
        return
    top_domain, top_count = c.most_common(1)[0]
    log("STATS", f"total: {len(items)} | top domains: {top_domain}:{top_count}")

def main() -> None:
    print("[BOOT] starting aggregator")
    print(f"[BOOT] version: {VER}")
    print(f"[BOOT] python: {sys.version.split()[0]}")
    print(f"[BOOT] cwd  = {ROOT}")
    cfg = load_cfg()
    sources = cfg.get("sources") or []
    print(f"[RUN] sources: {len(sources)}")
    fresh = collect(sources)
    log("INFO", f"fresh after aggregate: {len(fresh)}")
    existing = read_existing()
    log("INFO", f"existing in file: {len(existing)}")
    preserve_stable_identity(fresh, existing)
    merged = dedup_by_link(fresh + existing)
    merged = sort_by_date(merged)
    new_count = len(merged) - len(existing)
    log("INFO", f"new items this run: {new_count}")
    if len(merged) > 5000:
        merged = merged[:5000]
    log("INFO", f"merged total (<= 5000): {len(merged)}")
    stats(merged)
    save(merged)
    log("DONE", f"saved {len(merged)} items -> {NEWS_JSON}")
    log("DONE", f"meta  -> {META_JSON}")
    print("[BOOT] done")

if __name__ == "__main__":
    main()
