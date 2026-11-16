"""Owner-reviewable calculator campaign links for short videos.

Offline-only; no publisher imports, tracking calls, or automatic caption edits.
"""
from __future__ import annotations

import re
from urllib.parse import urlencode, urlsplit, urlunsplit

SITE_HOST = "spec-avtoportal.ru"
TARGETS = {
    "axis_distribution": "/tools/raspredelenie-gruza-po-osyam/",
    "axle_load": "/tools/nagruzka-na-os/",
    "trip_cost": "/tools/stoimost-reysa/",
}
PLATFORMS = ("youtube", "instagram", "tiktok")
CAMPAIGN = "calculator_short_202611"
_TOKEN = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")


def _safe_token(value: str, name: str) -> str:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase ASCII token (1-64 chars)")
    return value


def calculator_link(*, platform: str, target: str, content_id: str) -> str:
    """Return an allowlisted URL with unambiguous, stable attribution tags."""
    platform = _safe_token(platform, "platform")
    content_id = _safe_token(content_id, "content_id")
    if platform not in PLATFORMS:
        raise ValueError("unknown platform")
    if target not in TARGETS:
        raise ValueError("unknown calculator target")
    # Fixed HTTPS origin and path: no host/path from user-provided content.
    base = urlsplit("https://" + SITE_HOST + TARGETS[target])
    query = urlencode({
        "utm_source": platform,
        "utm_medium": "video",
        "utm_campaign": CAMPAIGN,
        "utm_content": content_id,
    })
    return urlunsplit((base.scheme, base.netloc, base.path, query, ""))


def preview_package(*, target: str, content_id: str) -> dict:
    if target not in TARGETS:
        raise ValueError("unknown calculator target")
    # Validate content_id before producing any partial output.
    _safe_token(content_id, "content_id")
    links = {platform: calculator_link(platform=platform, target=target, content_id=content_id)
             for platform in PLATFORMS}
    return {
        "schema": 1,
        "status": "owner_review_required",
        "production_effect": "none",
        "publish_called": False,
        "paid_api_calls": 0,
        "target": target,
        "content_id": content_id,
        "links": links,
        "platform_guidance": {
            "youtube": "Use tracked link in description and optionally a supported profile/link surface; verify tap path in app.",
            "instagram": "Reel caption URL is generally not clickable. Point on-screen CTA to an active profile link; update/check the link manually and verify with a test tap.",
            "tiktok": "Do not assume video-caption links are clickable. Verify account's website/profile link eligibility and the actual link destination.",
        },
        "measurement": {
            "report": "Yandex Metrica -> Sources -> UTM tags (utm_campaign and utm_source)",
            "campaign": CAMPAIGN,
            "count": "visits, users and goals separately; do not mistake pageviews for visits",
            "caveat": "A generated link or a video view does not prove a website visit.",
        },
    }
