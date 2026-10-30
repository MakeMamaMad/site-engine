"""Offline importer for owner-authorized Metricool per-post report responses.

Metricool's "videos published in range" (YT), "reels" (IG) and "posts"
(TikTok) connectors are per-publication observations, not daily evolution.
No network calls, API credentials, scheduling or publishing.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .analytics import parse_count

SCHEMAS = {
    "youtube": ("YTVP02", "YTVP05", "YTVP06", "YTVP17"),
    "instagram": ("IGRE02", "IGRE06", "IGRE23"),
    "tiktok": ("TKPO02", "TKPO03", "TKPO07"),
}
SOURCE = "metricool_owner_connected"
# Use a documented timezone for date strings supplied without any offset.
# The account's local timezone is Europe/Minsk; dates near DST changes require
# checking provider metadata before using in a post-age comparison.
ACCOUNT_TIMEZONE = "Europe/Minsk"


def import_posts(platform: str, payload: dict[str, Any], *,
                 metric_ids: list[str], collected_at: str,
                 account_timezone: str = ACCOUNT_TIMEZONE) -> dict[str, Any]:
    if platform not in SCHEMAS:
        raise ValueError("Unsupported platform")
    if tuple(metric_ids) != SCHEMAS[platform]:
        raise ValueError("Metric IDs/order do not match validated Metricool query")
    collected = datetime.fromisoformat(collected_at.replace("Z", "+00:00"))
    if collected.tzinfo is None:
        raise ValueError("collected_at must include timezone")
    if not isinstance(payload.get("rows"), list):
        raise ValueError("Expected rows array")
    from zoneinfo import ZoneInfo
    zone = ZoneInfo(account_timezone)
    posts, rejected = [], []
    seen = set()
    for index, row in enumerate(payload["rows"], 1):
        try:
            if not isinstance(row, list) or len(row) != len(metric_ids):
                raise ValueError("Invalid row shape")
            raw_date, raw_url, raw_views = row[:3]
            local_date = datetime.strptime(str(raw_date), "%Y%m%d%H%M%S")
            published = local_date.replace(tzinfo=zone).astimezone(timezone.utc)
            raw_url = str(raw_url or "").strip()
            parts = urlsplit(raw_url)
            allowed = {"youtube": ("youtube.com", "youtu.be"),
                       "instagram": ("instagram.com",),
                       "tiktok": ("tiktok.com",)}[platform]
            host = (parts.hostname or "").lower()
            if parts.scheme != "https" or not any(host == h or host.endswith("." + h) for h in allowed):
                raise ValueError("Unexpected post URL/domain")
            post_url = urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))
            if post_url in seen:
                raise ValueError("Duplicate platform URL")
            seen.add(post_url)
            # No content ID supplied by Metricool. Matching requires owner
            # mapping; timestamp proximity is NEVER authoritative linkage.
            views = None if raw_views is None or str(raw_views).strip() == "" else parse_count(raw_views, "views")
            posts.append({
                "platform": platform,
                "post_url": post_url,
                "published_at": published.isoformat(),
                "published_at_source": str(raw_date),
                "timezone_assumption": account_timezone,
                "views": views,
                "title": str(row[3]).strip() if platform == "youtube" and row[3] is not None else None,
                "collected_at": collected.astimezone(timezone.utc).isoformat(),
                "content_id": None,
                "match_status": "requires_explicit_owner_mapping",
                "source": SOURCE,
                "classification": "real_per_post_metricool_snapshot",
            })
        except (ValueError, TypeError) as exc:
            rejected.append({"row": index, "reason": str(exc)})
    return {
        "platform": platform, "schema": 1, "metric_ids": metric_ids,
        "source": SOURCE, "collected_at": collected.isoformat(),
        "posts": posts, "rejected": rejected,
        "warnings": [
            "Per-post view definitions differ by platform.",
            "Missing video view values are unknown, not zero.",
            "Publication times were localized using an explicit account timezone assumption.",
            "No content IDs: do not match by time or title alone.",
            "View snapshot is not a historical 24h/7d post-age snapshot.",
        ],
    }


def apply_owner_mapping(imports: list[dict[str, Any]], mapping: dict[str, str]) -> dict[str, Any]:
    """Map normalized platform URLs to explicitly approved site content IDs."""
    result = []
    for batch in imports:
        for post in batch["posts"]:
            row = dict(post)
            content_id = mapping.get(row["post_url"])
            if content_id is not None:
                if not isinstance(content_id, str) or not content_id.strip():
                    raise ValueError("Content ID must be a nonblank string")
                row["content_id"] = content_id.strip()
                row["match_status"] = "explicit_owner_mapping"
            result.append(row)
    return {
        "schema": 1,
        "type": "per_post_current_snapshot",
        "observations": result,
        "unmapped": sum(p["content_id"] is None for p in result),
        "source": SOURCE,
        "advisory_only": True,
        "publication_effect": "none",
        "warnings": [
            "Unmapped posts are excluded from cross-platform article matching.",
            "Snapshots captured at different ages cannot be compared as equal-window performance.",
            "Do not feed these results into the 24h/7d matcher without age-aligned snapshots.",
        ],
    }


def load_response(path: str | Path) -> dict[str, Any]:
    result = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError("Expected JSON object")
    return result
