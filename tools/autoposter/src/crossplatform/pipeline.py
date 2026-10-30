"""Feature flag and read-only combined review for Cross-Platform Growth v1."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .analytics import OWNER_BASELINE_SNAPSHOT, build_cross_platform_report, ingest_observations
from .hooks import build_platform_packages


FLAG = "CROSS_PLATFORM_GROWTH_ENABLED"


def is_enabled(value: str | None = None) -> bool:
    if value is None:
        value = os.getenv(FLAG, "0")
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _disabled() -> dict[str, Any]:
    return {
        "schema": 1,
        "enabled": False,
        "status": "disabled",
        "flag": FLAG,
        "advisory_only": True,
        "publishing_invoked": False,
        "scheduling_effect": "none",
        "production_weights_changed": False,
        "production_narration_changed": False,
    }


def build_cross_platform_review(
    *,
    observation_rows: list[dict[str, Any]],
    article: dict[str, Any],
    storyboard: Any = None,
    candidate_rewrites: dict[str, list[str]] | None = None,
    video: Path | None = None,
    visual_output_dir: Path | None = None,
    enabled: bool | None = None,
) -> dict[str, Any]:
    """Combine the three modules. Returns a disabled stub unless the flag is on
    (or ``enabled=True`` is passed explicitly by a preview)."""
    active = is_enabled() if enabled is None else bool(enabled)
    if not active:
        return _disabled()
    analytics = build_cross_platform_report(ingest_observations(observation_rows), owner_context=OWNER_BASELINE_SNAPSHOT)
    hooks = build_platform_packages(article, storyboard=storyboard, candidate_rewrites=candidate_rewrites)
    visual = None
    if video is not None and visual_output_dir is not None:
        from .visual_qa import run_visual_qa  # needs ffmpeg; imported only when used

        visual = run_visual_qa(video=video, output_dir=visual_output_dir)
    return {
        "schema": 1,
        "enabled": True,
        "status": "advisory_review_ready",
        "advisory_only": True,
        "publishing_invoked": False,
        "scheduling_effect": "none",
        "production_weights_changed": False,
        "production_narration_changed": False,
        "analytics": analytics,
        "platform_packages": hooks,
        "visual_qa": visual,
        "owner_approval_required": True,
    }
