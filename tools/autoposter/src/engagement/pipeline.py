"""Shared disabled-by-default interface for engagement drafts."""
from __future__ import annotations

import os
from typing import Any

from .comment import draft_comments
from .dm import prepare_dm
from .reply import classify_comments


def is_enabled(value: str | None = None) -> bool:
    value = os.getenv("INSTAGRAM_ENGAGEMENT_ENABLED", "0") if value is None else value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def build_engagement_drafts(*, comment_request: dict[str, Any], imported_comments: list[dict[str, Any]], dm_request: dict[str, Any], enabled: bool | None = None) -> dict[str, Any]:
    active = is_enabled() if enabled is None else bool(enabled)
    safety = {"read_only": True, "network_accessed": False, "auto_posted": False, "auto_replied": False, "dm_sent": False, "scheduled": False, "approval_required": True}
    if not active:
        return {"status": "disabled", "enabled": False, "comments": None, "replies": None, "dm": None, **safety}
    return {
        "status": "drafts_ready", "enabled": True,
        "comments": draft_comments(**comment_request),
        "replies": classify_comments(imported_comments),
        "dm": prepare_dm(dm_request), **safety,
    }
