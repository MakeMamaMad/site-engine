"""Opt-in, preview-only orchestration for Instagram profile and static formats."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .carousel import build_carousel, render_carousel
from .profile import audit_profile
from .story import build_story_sequence, render_story_sequence


def is_enabled(value: str | None = None) -> bool:
    if value is None:
        value = os.getenv("INSTAGRAM_FORMATS_ENABLED", "0")
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def build_formats_preview(
    *, profile: dict[str, Any], source: dict[str, Any], output_dir: Path,
    enabled: bool | None = None,
) -> dict[str, Any]:
    active = is_enabled() if enabled is None else bool(enabled)
    safety = {
        "publishing_invoked": False,
        "profile_modified": False,
        "messages_sent": False,
        "scheduling_effect": "none",
        "production_state_changed": False,
    }
    if not active:
        return {
            "schema": 1, "enabled": False, "status": "disabled", "advisory_only": True,
            "profile": None, "carousel": None, "stories": None, **safety,
        }
    profile_report = audit_profile(profile)
    carousel = build_carousel(source)
    stories = build_story_sequence(source)
    carousel_render = render_carousel(carousel, output_dir / "carousel")
    story_render = render_story_sequence(stories, output_dir / "stories")
    return {
        "schema": 1,
        "enabled": True,
        "status": "preview_ready",
        "advisory_only": True,
        "profile": profile_report,
        "carousel": {"package": carousel, "render": carousel_render},
        "stories": {"package": stories, "render": story_render},
        **safety,
    }
