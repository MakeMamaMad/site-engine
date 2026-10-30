"""Explicit publication receipts link Metricool post URLs to Short v2 content keys.

No time/title guessing, scraping, credentials, post creation or production imports.
Receipts may be written by authorized publisher integrations later, but this
module only validates supplied data and emits an owner-reviewable mapping.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

PLATFORM_HOSTS = {
    "youtube": ("youtube.com", "youtu.be"),
    "instagram": ("instagram.com",),
    "tiktok": ("tiktok.com",),
}


def canonical_post_url(platform: str, url: str) -> str:
    if platform not in PLATFORM_HOSTS:
        raise ValueError("unknown platform")
    parts = urlsplit(str(url).strip())
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not any(host == h or host.endswith("." + h) for h in PLATFORM_HOSTS[platform]):
        raise ValueError("unexpected post URL")
    path = parts.path.rstrip("/")
    query = ""
    if platform == "youtube":
        if host == "youtu.be":
            video_id = path.removeprefix("/")
        else:
            ids = parse_qs(parts.query).get("v", [])
            video_id = ids[0] if ids else ""
        import re
        if not re.fullmatch(r"[a-zA-Z0-9_-]{11}", video_id):
            raise ValueError("invalid YouTube video id")
        host, path = "www.youtube.com", "/watch"
        query = urlencode({"v": video_id})
    if platform == "instagram" and not path.startswith("/reel/"):
        raise ValueError("not a Reel URL")
    if platform == "tiktok" and "/video/" not in path:
        raise ValueError("not a TikTok video URL")
    return urlunsplit(("https", host, path, query, ""))


def receipt_mapping(manifests: list[dict[str, Any]], receipts: list[dict[str, Any]]) -> dict[str, Any]:
    """Build URL->content_key only when a receipt explicitly identifies render key.

    A manifest proves a video rendering happened; a publication receipt must
    independently prove which URL was actually published for that render.
    """
    keys = {str(m.get("content_key", "")).strip() for m in manifests if m.get("content_key")}
    if not keys:
        raise ValueError("no valid manifest content keys")
    mapping: dict[str, str] = {}
    rejected: list[dict[str, Any]] = []
    for i, receipt in enumerate(receipts, 1):
        try:
            key = str(receipt.get("content_key") or "").strip()
            if key not in keys:
                raise ValueError("content_key not backed by manifest")
            platform = str(receipt["platform"]).strip().lower()
            url = canonical_post_url(platform, str(receipt["post_url"]))
            if url in mapping and mapping[url] != key:
                raise ValueError("conflicting URL to content_key")
            if url in mapping:
                raise ValueError("duplicate receipt")
            mapping[url] = key
        except (KeyError, ValueError, TypeError) as exc:
            rejected.append({"receipt_index": i, "error": str(exc)})
    return {
        "schema": 1,
        "type": "owner_verified_publication_receipt_mapping",
        "url_to_content_id": mapping,
        "rejected": rejected,
        "unmapped_posts_remain_unknown": True,
        "advisory_only": True,
        "warnings": [
            "Do not infer receipt linkage from titles or upload timestamps.",
            "Source receipts must come from the owned publishing workflow or explicit owner confirmation.",
            "No auto-publishing, scheduling or channel configuration is changed.",
        ],
    }


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))
