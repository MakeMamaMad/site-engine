"""Read-only importer for Metricool daily EVOLUTION metrics, not per-post Insights.

Consumes owner-exported JSON response bodies from Metricool analytics queries.
Does not authenticate, call external APIs, schedule, publish, or enable any flag.
Never passes daily totals to the per-post matcher in analytics.py.
"""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

FIELD_IDS = {
    "youtube": {"views": "YTEV02", "followers": "YTEV01"},
    "instagram": {"views": "IGEV23", "followers": "IGEV01"},
    "tiktok": {"views": "TKEV02", "followers": "TKEV07"},
}
REQUIRED_SOURCE = "metricool_owner_connected"
CLASSIFICATION = "real_daily_platform_metrics_not_per_post"


def _number(value: Any, *, field: str) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field}: boolean value")
    try:
        number = float(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{field}: not a number: {value!r}") from exc
    if not math.isfinite(number) or number < 0 or not number.is_integer():
        raise ValueError(f"{field}: invalid count {value!r}")
    return int(number)


def import_metricool_daily(
    platform: str,
    payload: dict[str, Any],
    *,
    metric_ids: list[str],
    collected_at: str,
    source: str = REQUIRED_SOURCE,
) -> dict[str, Any]:
    """Import a response with rows ordered exactly as metric_ids + YYYYMMDD.

    The Metricool query's metrics argument defines column order; the final
    YYYYMMDD column is the day. An empty rows array is not zero traffic.
    """
    if platform not in FIELD_IDS:
        raise ValueError("Unsupported platform")
    if source != REQUIRED_SOURCE:
        raise ValueError("Unexpected source")
    parsed_at = datetime.fromisoformat(collected_at.replace("Z", "+00:00"))
    if parsed_at.tzinfo is None:
        raise ValueError("collected_at requires timezone")
    required = list(FIELD_IDS[platform].values())
    if metric_ids != required:
        raise ValueError(f"Expected metric_ids in this order: {required}")
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ValueError("Metricool payload missing rows")
    days: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, list) or len(row) != len(metric_ids) + 1:
            raise ValueError("Unexpected row shape")
        try:
            day = datetime.strptime(str(row[-1]), "%Y%m%d").date().isoformat()
        except ValueError as exc:
            raise ValueError(f"Invalid day: {row[-1]!r}") from exc
        if day in days:
            raise ValueError(f"Duplicate day: {day}")
        days[day] = {
            "date": day,
            "views": _number(row[0], field="views"),
            "followers": _number(row[1], field="followers"),
        }
    ordered = [days[d] for d in sorted(days)]
    daily_views = [d["views"] for d in ordered if d["views"] is not None]
    follower_observations = [d for d in ordered if d["followers"] is not None]
    return {
        "schema": 1,
        "platform": platform,
        "source": source,
        "classification": CLASSIFICATION,
        "collected_at": parsed_at.isoformat(),
        "metric_ids": metric_ids,
        "daily": ordered,
        "summary": {
            "observed_days": len(ordered),
            "days_with_views": len(daily_views),
            "sum_daily_views": sum(daily_views) if daily_views else None,
            "latest_followers": follower_observations[-1]["followers"] if follower_observations else None,
            "latest_followers_as_of": follower_observations[-1]["date"] if follower_observations else None,
        },
        "warnings": (
            ["no_rows_returned_not_equivalent_to_zero"] if not ordered else []
        ) + (
            ["daily_aggregate_not_post_level_or_cross_platform_comparable"]
        ),
    }


def load_metricool_response(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Expected Metricool JSON object")
    return payload


def build_daily_report(imports: list[dict[str, Any]]) -> dict[str, Any]:
    if len({item["platform"] for item in imports}) != len(imports):
        raise ValueError("Duplicate platforms")
    return {
        "schema": 1,
        "type": "daily_platform_observations",
        "imports": imports,
        "advisory_only": True,
        "not_post_level": True,
        "website_attribution": "unavailable",
        "warnings": [
            "Platform view definitions differ: do not rank raw totals as equivalent.",
            "Metricool daily evolution is not a per-video snapshot; content matching is unavailable.",
            "Missing dates/values are unknown, not zero. No automatic Metricool API access is implemented.",
        ],
    }
