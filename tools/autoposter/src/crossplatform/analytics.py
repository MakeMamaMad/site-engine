"""Offline cross-platform analytics for YouTube Shorts, Instagram Reels and TikTok.

Owner-supplied CSV/JSON observations only. Every observation is one metric
snapshot of one platform post at one collection time. The module:

- validates timestamps and metric values and keeps the raw input row;
- tracks which optional metrics are missing instead of inferring them;
- removes exact duplicate snapshots and quarantines conflicting ones;
- keeps later snapshots of the same post as updates (a time series);
- matches publications across platforms only by explicit content/article ID;
- compares platforms only at equivalent post-age windows and warns otherwise;
- normalizes each post against its own platform baseline before any
  cross-platform statement, because view definitions differ by platform;
- keeps descriptive observations separate from noncausal hypotheses;
- never attributes website traffic.
"""
from __future__ import annotations

import csv
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from ..intelligence.common import median


PLATFORMS = ("youtube", "instagram", "tiktok")
PLATFORM_ALIASES = {
    "youtube": "youtube", "yt": "youtube", "youtube_shorts": "youtube", "shorts": "youtube",
    "instagram": "instagram", "ig": "instagram", "instagram_reels": "instagram", "reels": "instagram",
    "tiktok": "tiktok", "tt": "tiktok", "tik_tok": "tiktok",
}
PLATFORM_HOSTS = {
    "youtube": ("youtube.com", "youtu.be"),
    "instagram": ("instagram.com",),
    "tiktok": ("tiktok.com",),
}

COUNT_METRICS = (
    "views", "engaged_views", "reach", "likes", "comments", "shares", "saves",
    "followers_gained", "profile_visits", "website_clicks",
)
SECONDS_METRICS = ("watch_time_seconds", "average_watch_duration_seconds")
PERCENT_METRICS = ("average_percentage_viewed", "completion_rate")
OPTIONAL_METRICS = tuple(m for m in COUNT_METRICS + SECONDS_METRICS + PERCENT_METRICS if m != "views")
ALL_METRICS = ("views",) + OPTIONAL_METRICS
# Counters that a platform reports cumulatively; a decrease between snapshots
# is possible (spam filtering) but must be visible.
CUMULATIVE_METRICS = ("views", "engaged_views", "likes", "comments", "shares", "saves", "followers_gained", "watch_time_seconds")

# Metrics that only exist on one platform. They are never used for another
# platform and never placed side by side with another platform's views.
PLATFORM_ONLY_METRICS = {"engaged_views": "youtube"}

FIELD_ALIASES = {
    "content_id": ("content_id", "canonical_content_id", "article_id", "source_id", "canonical_id"),
    "platform": ("platform",),
    "post_id": ("post_id", "platform_post_id", "video_id", "media_id"),
    "post_url": ("post_url", "url", "permalink", "platform_url"),
    "published_at": ("published_at", "publication_timestamp", "publish_time", "posted_at"),
    "collected_at": ("collected_at", "metric_collection_timestamp", "metrics_collected_at", "snapshot_at"),
    "dataset_label": ("dataset_label", "data_classification"),
    "views": ("views", "plays", "video_views"),
    "engaged_views": ("engaged_views",),
    "reach": ("reach", "accounts_reached", "reached_audience"),
    "watch_time_seconds": ("watch_time_seconds", "total_watch_time_seconds"),
    "watch_time_hours": ("watch_time_hours",),
    "average_watch_duration_seconds": ("average_watch_duration_seconds", "average_view_duration_seconds", "avg_watch_time_seconds"),
    "average_percentage_viewed": ("average_percentage_viewed", "avg_percentage_viewed"),
    "completion_rate": ("completion_rate", "full_video_watched_rate"),
    "likes": ("likes",),
    "comments": ("comments",),
    "shares": ("shares",),
    "saves": ("saves", "favorites"),
    "followers_gained": ("followers_gained", "subscribers_gained", "follows"),
    "profile_visits": ("profile_visits", "profile_views"),
    "website_clicks": ("website_clicks", "link_clicks"),
}

STANDARD_WINDOWS = (("24h", 24.0), ("72h", 72.0), ("7d", 168.0), ("28d", 672.0))
MIN_BASELINE_SAMPLE = 5
PUBLICATION_GAP_WARNING_HOURS = 24.0

METRIC_DEFINITIONS = {
    "youtube": {
        "views": "YouTube Shorts views as exported from YouTube Studio. Since 2025 Shorts views count plays/replays; this is not the same definition as Instagram or TikTok views.",
        "engaged_views": "YouTube-only engaged views. Never compared with Instagram or TikTok views.",
    },
    "instagram": {
        "views": "Instagram Reels views as shown in owner-exported Insights. Definition is Instagram's own and is not equivalent to YouTube or TikTok views.",
    },
    "tiktok": {
        "views": "TikTok video views as shown in owner-exported analytics. Definition is TikTok's own and is not equivalent to YouTube or Instagram views.",
    },
}


class AnalyticsDataError(ValueError):
    """Imported cross-platform data failed deterministic validation."""


# ---------------------------------------------------------------- loading

def load_observation_rows(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = data.get("observations", [])
        if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
            raise AnalyticsDataError(f"{path}: JSON must be a list of objects or {{'observations': [...]}}")
        return data
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    raise AnalyticsDataError(f"{path}: only .csv and .json are supported")


# ---------------------------------------------------------------- parsing

def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _pick(row: dict[str, Any], field: str) -> tuple[str | None, Any]:
    lowered = {str(k).strip().lower(): v for k, v in row.items()}
    for alias in FIELD_ALIASES.get(field, (field,)):
        if alias in lowered and not _blank(lowered[alias]):
            return alias, lowered[alias]
    return None, None


def parse_timestamp(value: Any, field: str) -> tuple[datetime, str]:
    """Return an aware UTC datetime and its precision ("second" or "day")."""
    text = str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        try:
            parsed = datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise AnalyticsDataError(f"{field}: invalid date {value!r}") from exc
        return parsed, "day"
    candidate = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise AnalyticsDataError(f"{field}: not an ISO 8601 timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise AnalyticsDataError(f"{field}: timezone offset required (e.g. +03:00 or Z): {value!r}")
    return parsed.astimezone(timezone.utc), "second"


def parse_count(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise AnalyticsDataError(f"{field}: boolean is not a count")
    if isinstance(value, int):
        number = value
    elif isinstance(value, float):
        if not math.isfinite(value) or value != int(value):
            raise AnalyticsDataError(f"{field}: count must be a whole number, got {value!r}")
        number = int(value)
    else:
        text = str(value).strip().replace(" ", "").replace(" ", "").replace(" ", "").replace("_", "")
        if not re.fullmatch(r"-?\d+", text):
            raise AnalyticsDataError(
                f"{field}: count must be a whole number without abbreviations or separators, got {value!r}"
            )
        number = int(text)
    if number < 0:
        raise AnalyticsDataError(f"{field}: cannot be negative, got {value!r}")
    return number


def parse_nonnegative(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise AnalyticsDataError(f"{field}: boolean is not a number")
    text = str(value).strip().replace(" ", "")
    if not re.fullmatch(r"-?\d+(?:[.,]\d+)?", text):
        raise AnalyticsDataError(f"{field}: must be a number, got {value!r}")
    number = float(text.replace(",", "."))
    if not math.isfinite(number) or number < 0:
        raise AnalyticsDataError(f"{field}: must be a finite nonnegative number, got {value!r}")
    return number


def parse_percent(value: Any, field: str) -> tuple[float, str]:
    """Percent points. ``71%`` and ``71`` mean 71; a decimal below 1 (``0.71``)
    is read as a fraction and the interpretation is recorded."""
    text = str(value).strip().replace(" ", "")
    explicit = text.endswith("%")
    number = parse_nonnegative(text.rstrip("%"), field)
    interpretation = "percent"
    if not explicit and number < 1 and re.search(r"[.,]", text):
        number *= 100
        interpretation = "fraction_to_percent"
    upper = 100.0 if field == "completion_rate" else 1000.0
    if number > upper:
        raise AnalyticsDataError(f"{field}: {number:g}% exceeds the plausible maximum of {upper:g}%")
    return round(number, 6), interpretation


def canonical_post_key(platform: str, post_id: str | None, post_url: str | None) -> tuple[str, str | None]:
    """Return ``platform:<id>`` and the platform ID extracted from the URL."""
    url_id: str | None = None
    if post_url:
        parsed = urlparse(post_url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise AnalyticsDataError(f"post_url must be an absolute http(s) URL: {post_url!r}")
        host = parsed.netloc.lower().split(":")[0]
        host = host[4:] if host.startswith("www.") else host
        host = host[2:] if host.startswith("m.") else host
        if not any(host == allowed or host.endswith("." + allowed) for allowed in PLATFORM_HOSTS[platform]):
            raise AnalyticsDataError(f"post_url host {host!r} does not belong to platform {platform!r}")
        parts = [part for part in parsed.path.split("/") if part]
        if platform == "youtube":
            if host == "youtu.be" and parts:
                url_id = parts[0]
            elif len(parts) >= 2 and parts[0] in {"shorts", "embed", "live"}:
                url_id = parts[1]
            else:
                url_id = (parse_qs(parsed.query).get("v") or [None])[0]
        elif platform == "instagram":
            for marker in ("reel", "reels", "p", "tv"):
                if marker in parts and parts.index(marker) + 1 < len(parts):
                    url_id = parts[parts.index(marker) + 1]
                    break
        elif platform == "tiktok":
            if "video" in parts and parts.index("video") + 1 < len(parts):
                url_id = parts[parts.index("video") + 1]
        if not url_id:
            url_id = f"url:{host}/{'/'.join(parts)}"
    identifier = str(post_id).strip() if post_id else url_id
    if not identifier:
        raise AnalyticsDataError("platform post ID or post URL is required")
    return f"{platform}:{identifier}", url_id


def normalize_observation(row: dict[str, Any], index: int) -> dict[str, Any]:
    """Validate one input row. Raises AnalyticsDataError with every problem found."""
    errors: list[str] = []
    notes: list[dict[str, str]] = []

    def required(field: str) -> Any:
        _, value = _pick(row, field)
        if value is None:
            errors.append(f"{field} is required")
        return value

    content_id = required("content_id")
    platform_raw = required("platform")
    platform = PLATFORM_ALIASES.get(str(platform_raw or "").strip().lower()) if platform_raw else None
    if platform_raw and not platform:
        errors.append(f"platform must be one of {', '.join(PLATFORMS)}, got {platform_raw!r}")
    _, post_id = _pick(row, "post_id")
    _, post_url = _pick(row, "post_url")
    if post_id is None and post_url is None:
        errors.append("platform post ID or post URL is required")

    published = collected = None
    published_precision = collected_precision = None
    for field in ("published_at", "collected_at"):
        value = required(field)
        if value is None:
            continue
        try:
            parsed, precision = parse_timestamp(value, field)
        except AnalyticsDataError as exc:
            errors.append(str(exc))
            continue
        if field == "published_at":
            published, published_precision = parsed, precision
        else:
            collected, collected_precision = parsed, precision
    if collected_precision == "day":
        errors.append("collected_at must include time and timezone, not only a date")
    if published and collected and collected < published:
        errors.append("collected_at is earlier than published_at")

    metrics: dict[str, Any] = {name: None for name in ALL_METRICS}
    for name in COUNT_METRICS:
        _, value = _pick(row, name)
        if value is None:
            if name == "views":
                errors.append("views is required")
            continue
        try:
            metrics[name] = parse_count(value, name)
        except AnalyticsDataError as exc:
            errors.append(str(exc))
    for name in SECONDS_METRICS:
        _, value = _pick(row, name)
        if value is None and name == "watch_time_seconds":
            _, hours = _pick(row, "watch_time_hours")
            if hours is not None:
                try:
                    metrics[name] = round(parse_nonnegative(hours, "watch_time_hours") * 3600, 3)
                    notes.append({"field": name, "note": "converted_from_watch_time_hours"})
                except AnalyticsDataError as exc:
                    errors.append(str(exc))
            continue
        if value is None:
            continue
        try:
            metrics[name] = parse_nonnegative(value, name)
        except AnalyticsDataError as exc:
            errors.append(str(exc))
    for name in PERCENT_METRICS:
        _, value = _pick(row, name)
        if value is None:
            continue
        try:
            metrics[name], interpretation = parse_percent(value, name)
            if interpretation != "percent":
                notes.append({"field": name, "note": interpretation})
        except AnalyticsDataError as exc:
            errors.append(str(exc))

    post_key = url_id = None
    if platform and (post_id is not None or post_url is not None):
        try:
            post_key, url_id = canonical_post_key(platform, post_id, post_url)
        except AnalyticsDataError as exc:
            errors.append(str(exc))
        if post_id and url_id and not url_id.startswith("url:") and str(post_id).strip() != url_id:
            errors.append(f"post_id {post_id!r} does not match the ID in post_url ({url_id!r})")

    if errors:
        raise AnalyticsDataError("; ".join(errors))

    # Platform-only metrics are dropped for other platforms (kept in raw).
    for name, owner in PLATFORM_ONLY_METRICS.items():
        if metrics.get(name) is not None and platform != owner:
            notes.append({"field": name, "note": f"ignored_metric_not_defined_for_{platform}"})
            metrics[name] = None
    if metrics.get("engaged_views") is not None and metrics["engaged_views"] > metrics["views"]:
        notes.append({"field": "engaged_views", "note": "engaged_views_exceeds_views_check_export"})

    age_hours = (collected - published).total_seconds() / 3600 if published and collected else None
    _, label = _pick(row, "dataset_label")
    applicable = [m for m in OPTIONAL_METRICS if PLATFORM_ONLY_METRICS.get(m, platform) == platform]
    return {
        "row": index,
        "content_id": str(content_id).strip(),
        "platform": platform,
        "post_key": post_key,
        "post_id": str(post_id).strip() if post_id else url_id,
        "post_url": str(post_url).strip() if post_url else None,
        "published_at": published.isoformat().replace("+00:00", "Z") if published else None,
        "published_precision": published_precision,
        "collected_at": collected.isoformat().replace("+00:00", "Z") if collected else None,
        "age_hours": round(age_hours, 3) if age_hours is not None else None,
        "metrics": metrics,
        "missing_metrics": [m for m in applicable if metrics.get(m) is None],
        "dataset_label": str(label).strip() if label else "unlabeled",
        "notes": notes,
        "raw": dict(row),
    }


# ---------------------------------------------------------------- ingestion

def ingest_observations(rows: list[dict[str, Any]]) -> dict[str, Any]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        try:
            accepted.append(normalize_observation(row, index))
        except AnalyticsDataError as exc:
            rejected.append({"row": index, "errors": str(exc).split("; "), "raw": dict(row)})

    warnings: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []

    # Exact duplicates vs conflicting snapshots at the same collection time.
    by_snapshot: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for obs in accepted:
        by_snapshot.setdefault((obs["post_key"], obs["collected_at"]), []).append(obs)
    kept: list[dict[str, Any]] = []
    for (post_key, collected_at), group in by_snapshot.items():
        signatures = {json.dumps([g["content_id"], g["published_at"], g["metrics"]], sort_keys=True) for g in group}
        if len(signatures) == 1:
            kept.append(group[0])
            for extra in group[1:]:
                duplicates.append({"row": extra["row"], "duplicate_of_row": group[0]["row"], "post_key": post_key, "collected_at": collected_at})
        else:
            conflicts.append({
                "code": "conflicting_snapshot",
                "post_key": post_key,
                "collected_at": collected_at,
                "rows": [g["row"] for g in group],
                "detail": "Same post and collection time with different values; all versions excluded until the owner resolves the export.",
            })

    # A post must map to one content ID and one publication time.
    by_post: dict[str, list[dict[str, Any]]] = {}
    for obs in kept:
        by_post.setdefault(obs["post_key"], []).append(obs)
    clean: list[dict[str, Any]] = []
    for post_key, group in by_post.items():
        content_ids = sorted({g["content_id"] for g in group})
        published = sorted({g["published_at"] for g in group})
        if len(content_ids) > 1:
            conflicts.append({"code": "post_mapped_to_multiple_content_ids", "post_key": post_key, "content_ids": content_ids, "rows": [g["row"] for g in group]})
            continue
        if len(published) > 1:
            conflicts.append({"code": "inconsistent_published_at", "post_key": post_key, "published_at": published, "rows": [g["row"] for g in group]})
            continue
        group.sort(key=lambda g: g["collected_at"])
        for previous, current in zip(group, group[1:]):
            for metric in CUMULATIVE_METRICS:
                before, after = previous["metrics"].get(metric), current["metrics"].get(metric)
                if before is not None and after is not None and after < before:
                    warnings.append({
                        "code": "counter_decreased",
                        "post_key": post_key,
                        "metric": metric,
                        "from": {"collected_at": previous["collected_at"], "value": before},
                        "to": {"collected_at": current["collected_at"], "value": after},
                        "detail": "Kept as reported (platforms may remove filtered views); check the export.",
                    })
        clean.extend(group)

    clean.sort(key=lambda g: (g["content_id"], g["platform"], g["post_key"], g["collected_at"]))
    for obs in clean:
        if obs["published_precision"] == "day":
            warnings.append({"code": "published_at_date_only", "post_key": obs["post_key"], "row": obs["row"],
                             "detail": "Publication time known only to the day; windows shorter than 7d are not used for this post."})
    return {
        "observations": clean,
        "rejected": rejected,
        "duplicates": duplicates,
        "conflicts": conflicts,
        "warnings": _dedupe_warnings(warnings),
        "input_rows": len(rows),
    }


def _dedupe_warnings(warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result = []
    for warning in warnings:
        key = json.dumps({k: v for k, v in warning.items() if k != "row"}, sort_keys=True, ensure_ascii=False)
        if key not in seen:
            seen.add(key)
            result.append(warning)
    return result


# ---------------------------------------------------------------- windows

def window_tolerance_hours(window_hours: float) -> float:
    return max(3.0, window_hours * 0.15)


def snapshot_for_window(snapshots: list[dict[str, Any]], window_hours: float) -> dict[str, Any] | None:
    """Closest snapshot to the window age, if within tolerance."""
    tolerance = window_tolerance_hours(window_hours)
    eligible = []
    for snap in snapshots:
        uncertainty = 24.0 if snap["published_precision"] == "day" else 0.0
        if uncertainty > tolerance or snap["age_hours"] is None:
            continue
        distance = abs(snap["age_hours"] - window_hours)
        if distance <= tolerance:
            eligible.append((distance, snap["collected_at"], snap))
    if not eligible:
        return None
    eligible.sort(key=lambda item: (item[0], item[1]))
    return eligible[0][2]


def _posts(observations: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    posts: dict[str, list[dict[str, Any]]] = {}
    for obs in observations:
        posts.setdefault(obs["post_key"], []).append(obs)
    for group in posts.values():
        group.sort(key=lambda g: g["collected_at"])
    return posts


def _rate(numerator: Any, denominator: Any) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return round(numerator / denominator, 5)


def platform_baselines(observations: list[dict[str, Any]]) -> dict[str, Any]:
    posts = _posts(observations)
    result: dict[str, Any] = {}
    for platform in PLATFORMS:
        platform_posts = {key: snaps for key, snaps in posts.items() if snaps[0]["platform"] == platform}
        coverage = {}
        for metric in OPTIONAL_METRICS:
            if PLATFORM_ONLY_METRICS.get(metric, platform) != platform:
                continue
            latest = [snaps[-1] for snaps in platform_posts.values()]
            present = sum(1 for snap in latest if snap["metrics"].get(metric) is not None)
            coverage[metric] = {"present": present, "posts": len(latest)}
        windows = {}
        for label, hours in STANDARD_WINDOWS:
            values = []
            for key, snaps in platform_posts.items():
                snap = snapshot_for_window(snaps, hours)
                if snap:
                    values.append((key, snap))
            views = [snap["metrics"]["views"] for _, snap in values]
            med = median([float(v) for v in views])
            windows[label] = {
                "window_hours": hours,
                "tolerance_hours": window_tolerance_hours(hours),
                "posts": len(values),
                "median_views": med,
                "sample_sufficient": len(values) >= MIN_BASELINE_SAMPLE,
            }
        latest_rows = []
        for key, snaps in sorted(platform_posts.items()):
            snap = snaps[-1]
            m = snap["metrics"]
            latest_rows.append({
                "post_key": key,
                "content_id": snap["content_id"],
                "age_hours": snap["age_hours"],
                "snapshots": len(snaps),
                "views": m["views"],
                "engaged_views": m.get("engaged_views") if platform == "youtube" else None,
                "like_rate": _rate(m.get("likes"), m["views"]),
                "comment_rate": _rate(m.get("comments"), m["views"]),
                "share_rate": _rate(m.get("shares"), m["views"]),
                "save_rate": _rate(m.get("saves"), m["views"]),
                "follows_per_1000_views": round(m["followers_gained"] * 1000 / m["views"], 3) if m.get("followers_gained") is not None and m["views"] else None,
                "average_percentage_viewed": m.get("average_percentage_viewed"),
                "completion_rate": m.get("completion_rate"),
                "missing_metrics": snap["missing_metrics"],
            })
        result[platform] = {
            "posts": len(platform_posts),
            "snapshots": sum(len(s) for s in platform_posts.values()),
            "metric_definition": METRIC_DEFINITIONS[platform],
            "metric_coverage_latest_snapshot": coverage,
            "views_baseline_by_window": windows,
            "latest_snapshot_per_post": latest_rows,
        }
    return result


def match_content(observations: list[dict[str, Any]], baselines: dict[str, Any]) -> list[dict[str, Any]]:
    posts = _posts(observations)
    by_content: dict[str, dict[str, list[str]]] = {}
    for key, snaps in posts.items():
        by_content.setdefault(snaps[0]["content_id"], {}).setdefault(snaps[0]["platform"], []).append(key)

    results = []
    for content_id in sorted(by_content):
        platforms = by_content[content_id]
        warnings: list[dict[str, Any]] = []
        single: dict[str, list[dict[str, Any]]] = {}
        for platform, keys in sorted(platforms.items()):
            if len(keys) > 1:
                warnings.append({"code": "multiple_posts_on_platform", "platform": platform, "post_keys": sorted(keys),
                                 "detail": "Excluded from cross-platform comparison; compare these posts within the platform instead."})
            else:
                single[platform] = posts[keys[0]]
        present = [p for p in PLATFORMS if p in platforms]
        status = "matched_all_three" if len(present) == 3 else "partial_match" if len(present) == 2 else "single_platform"

        publications = {p: snaps[0]["published_at"] for p, snaps in single.items()}
        if len(publications) >= 2:
            times = sorted(datetime.fromisoformat(v.replace("Z", "+00:00")) for v in publications.values())
            gap = (times[-1] - times[0]).total_seconds() / 3600
            if gap > PUBLICATION_GAP_WARNING_HOURS:
                warnings.append({"code": "publication_time_gap", "hours": round(gap, 1), "published_at": publications,
                                 "detail": "Platforms published at different times; audience/day effects differ."})

        comparison = None
        if len(single) >= 2:
            common_window = None
            for label, hours in reversed(STANDARD_WINDOWS):
                snaps = {p: snapshot_for_window(s, hours) for p, s in single.items()}
                if all(snaps.values()):
                    common_window = (label, hours, snaps)
                    break
            if common_window:
                label, hours, snaps = common_window
                rows = {}
                for platform, snap in snaps.items():
                    base = baselines[platform]["views_baseline_by_window"][label]
                    views = snap["metrics"]["views"]
                    relative = None
                    reason = None
                    if not base["sample_sufficient"]:
                        reason = f"platform baseline has {base['posts']} posts at {label}; need {MIN_BASELINE_SAMPLE}"
                    elif base["median_views"]:
                        relative = round(views / base["median_views"], 3)
                    rows[platform] = {
                        "post_key": snap["post_key"],
                        "collected_at": snap["collected_at"],
                        "age_hours": snap["age_hours"],
                        "views": views,
                        "views_metric_definition": METRIC_DEFINITIONS[platform]["views"],
                        "platform_median_views_at_window": base["median_views"],
                        "relative_to_own_platform_median": relative,
                        "relative_unavailable_reason": reason,
                    }
                comparison = {
                    "comparable_window": label,
                    "window_hours": hours,
                    "tolerance_hours": window_tolerance_hours(hours),
                    "compared_metric": "views relative to each platform's own median",
                    "raw_views_directly_comparable": False,
                    "excluded_metrics": ["engaged_views (YouTube-only)"],
                    "platforms": rows,
                }
            else:
                ages = {p: [s["age_hours"] for s in snaps] for p, snaps in single.items()}
                warnings.append({"code": "window_mismatch", "snapshot_ages_hours": ages,
                                 "detail": "No standard window (24h/72h/7d/28d) has a snapshot for every platform; no cross-platform comparison is made."})
                comparison = {
                    "comparable_window": None,
                    "raw_views_directly_comparable": False,
                    "latest_snapshots_not_comparable": {
                        p: {"views": snaps[-1]["metrics"]["views"], "age_hours": snaps[-1]["age_hours"], "collected_at": snaps[-1]["collected_at"]}
                        for p, snaps in single.items()
                    },
                }
        results.append({
            "content_id": content_id,
            "match_status": status,
            "matched_by": "explicit content_id",
            "platforms_present": present,
            "platforms_missing": [p for p in PLATFORMS if p not in platforms],
            "post_keys": {p: sorted(keys) for p, keys in sorted(platforms.items())},
            "comparison": comparison,
            "warnings": warnings,
        })
    return results


# ---------------------------------------------------------------- report

def _observations_and_hypotheses(baselines: dict[str, Any], matches: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    descriptive: list[dict[str, Any]] = []
    hypotheses: list[dict[str, Any]] = []
    for platform in PLATFORMS:
        info = baselines[platform]
        for label, window in info["views_baseline_by_window"].items():
            if window["posts"]:
                descriptive.append({
                    "type": "descriptive",
                    "platform": platform,
                    "statement": f"{platform}: median views at {label} = {window['median_views']:g} across {window['posts']} posts"
                                 + ("" if window["sample_sufficient"] else " (sample below minimum; not a baseline)"),
                })
    for match in matches:
        comparison = match.get("comparison") or {}
        rows = comparison.get("platforms") or {}
        relative = {p: r["relative_to_own_platform_median"] for p, r in rows.items() if r["relative_to_own_platform_median"] is not None}
        if len(relative) >= 2:
            descriptive.append({
                "type": "descriptive",
                "content_id": match["content_id"],
                "statement": f"{match['content_id']} at {comparison['comparable_window']}: "
                             + ", ".join(f"{p} {v:.2f}x own median" for p, v in sorted(relative.items())),
            })
            best = max(relative, key=relative.get)
            worst = min(relative, key=relative.get)
            if relative[best] >= 1.5 and relative[worst] <= 0.8:
                hypotheses.append({
                    "type": "hypothesis",
                    "not_causal_evidence": True,
                    "content_id": match["content_id"],
                    "statement": f"Packaging or audience fit may differ: {best} outperformed its own median while {worst} underperformed. One item cannot establish a cause.",
                    "test_needed": "Repeat with several matched items and alternate hook/caption variants per platform before drawing conclusions.",
                    "confidence": "low",
                })
    return descriptive, hypotheses


def build_cross_platform_report(ingested: dict[str, Any], *, owner_context: dict[str, Any] | None = None) -> dict[str, Any]:
    observations = ingested["observations"]
    baselines = platform_baselines(observations)
    matches = match_content(observations, baselines)
    descriptive, hypotheses = _observations_and_hypotheses(baselines, matches)
    labels = sorted({obs["dataset_label"] for obs in observations})
    clicks = {
        p: sum(obs["metrics"]["website_clicks"] for obs in _latest(observations, p) if obs["metrics"].get("website_clicks") is not None)
        if any(obs["metrics"].get("website_clicks") is not None for obs in _latest(observations, p)) else None
        for p in PLATFORMS
    }
    warnings = list(ingested["warnings"])
    for match in matches:
        for warning in match["warnings"]:
            warnings.append({**warning, "content_id": match["content_id"]})
    return {
        "schema": 1,
        "module": "cross_platform_analytics",
        "advisory_only": True,
        "publishing_invoked": False,
        "production_weights_changed": False,
        "dataset_labels": labels,
        "dataset_quality": {
            "input_rows": ingested["input_rows"],
            "accepted_snapshots": len(observations),
            "rejected_rows": len(ingested["rejected"]),
            "exact_duplicates_removed": len(ingested["duplicates"]),
            "conflicts_quarantined": len(ingested["conflicts"]),
            "posts": len(_posts(observations)),
            "content_items": len({obs["content_id"] for obs in observations}),
            "minimum_baseline_sample": MIN_BASELINE_SAMPLE,
        },
        "rejected_rows": ingested["rejected"],
        "duplicates": ingested["duplicates"],
        "conflicts": ingested["conflicts"],
        "per_platform": baselines,
        "content_matching": matches,
        "descriptive_observations": descriptive,
        "noncausal_hypotheses": hypotheses,
        "website_traffic": {
            "attribution": "not_attributed",
            "platform_reported_website_clicks_latest": clicks,
            "detail": "Only platform-reported link clicks are listed. Site visits are not attributed to any platform or video.",
        },
        "owner_baseline_context": owner_context,
        "warnings": warnings,
        "limitations": [
            "View definitions differ by platform; raw views are never ranked across platforms.",
            "YouTube engaged views are YouTube-only and are not compared with Instagram or TikTok views.",
            "Cross-platform statements use each post's ratio to its own platform median at an equal post-age window.",
            "Metrics absent from the import stay absent; nothing is estimated or inferred.",
            "Descriptive observations are not causal findings; hypotheses require controlled repeats.",
        ],
    }


def _latest(observations: list[dict[str, Any]], platform: str) -> list[dict[str, Any]]:
    return [snaps[-1] for snaps in _posts(observations).values() if snaps[0]["platform"] == platform]


OWNER_BASELINE_SNAPSHOT = {
    "classification": "manual_owner_snapshot_not_comparable",
    "supplied_by": "owner (task brief)",
    "youtube": {"subscribers": 70, "subscribers_gained_28d": 25, "views_28d": 32200},
    "instagram": {"followers": 4, "posts": 71},
    "tiktok": {"followers": 1, "recent_visible_video_views_range": [65, 79]},
    "why_not_comparable": [
        "Channel-level totals, not per-post observations with publication and collection timestamps.",
        "Different scopes: YouTube is a 28-day aggregate; Instagram is a lifetime post count; TikTok is a visual range of recent videos.",
        "No explicit content IDs link these numbers across platforms.",
        "Instagram/TikTok Insights (reach, watch time, completion) were not supplied and are not inferred.",
    ],
}


def report_markdown(report: dict[str, Any]) -> str:
    q = report["dataset_quality"]
    lines = [
        "# Cross-platform performance report",
        "",
        f"> Dataset labels: {', '.join(report['dataset_labels']) or '—'}. Advisory only; nothing is published or reweighted.",
        "",
        f"Rows: {q['input_rows']} · accepted snapshots: {q['accepted_snapshots']} · rejected: {q['rejected_rows']} · "
        f"exact duplicates removed: {q['exact_duplicates_removed']} · conflicts quarantined: {q['conflicts_quarantined']} · "
        f"posts: {q['posts']} · content items: {q['content_items']}",
        "",
        "## Per-platform baselines (views, within platform only)",
        "",
        "| Platform | Posts | 24h median (n) | 72h median (n) | 7d median (n) | 28d median (n) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for platform in PLATFORMS:
        info = report["per_platform"][platform]
        cells = []
        for label, _ in STANDARD_WINDOWS:
            w = info["views_baseline_by_window"][label]
            if w["posts"]:
                cells.append(f"{w['median_views']:g} ({w['posts']}{'' if w['sample_sufficient'] else ', small'})")
            else:
                cells.append("—")
        lines.append(f"| {platform} | {info['posts']} | " + " | ".join(cells) + " |")
    lines += ["", "Metric definitions differ: " + " ".join(f"**{p}** — {report['per_platform'][p]['metric_definition']['views']}" for p in PLATFORMS), ""]
    lines += ["## Cross-platform matching (explicit content IDs)", "",
              "| Content ID | Status | Window | Relative to own platform median | Notes |", "|---|---|---|---|---|"]
    for match in report["content_matching"]:
        comp = match["comparison"] or {}
        rel = "—"
        if comp.get("platforms"):
            rel = ", ".join(
                f"{p}: {r['relative_to_own_platform_median']:.2f}x" if r["relative_to_own_platform_median"] is not None else f"{p}: n/a"
                for p, r in comp["platforms"].items()
            )
        notes = ", ".join(w["code"] for w in match["warnings"]) or "—"
        lines.append(f"| {match['content_id']} | {match['match_status']} | {comp.get('comparable_window') or 'none'} | {rel} | {notes} |")
    lines += ["", "## Descriptive observations", ""]
    lines += [f"- {row['statement']}" for row in report["descriptive_observations"]] or ["- None."]
    lines += ["", "## Noncausal hypotheses (require testing)", ""]
    lines += [f"- {row['statement']} Test: {row['test_needed']}" for row in report["noncausal_hypotheses"]] or ["- None."]
    lines += ["", "## Website traffic", "", f"- {report['website_traffic']['detail']}", ""]
    lines += ["## Data warnings", ""]
    lines += [f"- `{w['code']}` {w.get('post_key') or w.get('content_id') or ''} — {w.get('detail', '')}".rstrip(" —") for w in report["warnings"]] or ["- None."]
    if report["rejected_rows"]:
        lines += ["", "## Rejected rows", ""]
        lines += [f"- row {r['row']}: {'; '.join(r['errors'])}" for r in report["rejected_rows"]]
    if report["conflicts"]:
        lines += ["", "## Quarantined conflicts", ""]
        lines += [f"- `{c['code']}` {c['post_key']} rows {c['rows']}" for c in report["conflicts"]]
    ctx = report.get("owner_baseline_context")
    if ctx:
        lines += ["", "## Owner-supplied snapshot (context only, not part of the dataset)", "",
                  f"- YouTube: {ctx['youtube']['subscribers']} subscribers, +{ctx['youtube']['subscribers_gained_28d']} in 28 days, {ctx['youtube']['views_28d']} views in 28 days.",
                  f"- Instagram: {ctx['instagram']['followers']} followers, {ctx['instagram']['posts']} posts.",
                  f"- TikTok: {ctx['tiktok']['followers']} follower, recent visible videos around {ctx['tiktok']['recent_visible_video_views_range'][0]}–{ctx['tiktok']['recent_visible_video_views_range'][1]} views.",
                  "", "Not comparable because:"]
        lines += [f"- {reason}" for reason in ctx["why_not_comparable"]]
    lines += ["", "## Limitations", ""] + [f"- {item}" for item in report["limitations"]] + [""]
    return "\n".join(lines)
