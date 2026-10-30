"""Offline-first Instagram post analytics from owner-imported CSV or JSON."""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from .common import IntelligenceDataError, clean, median, strict_number


OPTIONAL_NUMBERS = (
    "reach", "shares", "saves", "follows", "average_watch_time_seconds",
    "three_second_retention", "non_follower_reach",
)


def load_audit_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".json":
        raw = json.loads(path.read_text(encoding="utf-8"))
        rows = raw.get("rows", raw) if isinstance(raw, dict) else raw
        if not isinstance(rows, list):
            raise IntelligenceDataError("audit JSON must contain a list or a rows list")
        return [dict(row) for row in rows if isinstance(row, dict)]
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _ratio(value: Any, field: str, row_number: int) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    raw = str(value).strip()
    percent = raw.endswith("%")
    if percent:
        raw = raw[:-1].strip()
    parsed = strict_number(raw, field, row_number, required=True)
    assert parsed is not None
    if percent or parsed > 1:
        parsed /= 100
    if not 0 <= parsed <= 1:
        raise IntelligenceDataError(f"row {row_number}: {field} must be between 0 and 1 or 0% and 100%")
    return parsed


def _validate_row(raw: dict[str, Any], row_number: int) -> dict[str, Any]:
    post_id = clean(raw.get("post_id") or raw.get("id"))
    if not post_id:
        raise IntelligenceDataError(f"row {row_number}: post_id is required")
    views = strict_number(raw.get("views"), "views", row_number, required=True)
    assert views is not None
    if not views.is_integer():
        raise IntelligenceDataError(f"row {row_number}: views must be a whole count")
    publication_date = clean(raw.get("publication_date") or raw.get("published_at"))
    if publication_date:
        try:
            date.fromisoformat(publication_date[:10])
        except ValueError as exc:
            raise IntelligenceDataError(f"row {row_number}: publication_date must use YYYY-MM-DD") from exc
    result: dict[str, Any] = {
        "post_id": post_id,
        "source_url": clean(raw.get("source_url") or raw.get("url")),
        "dataset_label": clean(raw.get("dataset_label")) or "owner_imported_metrics",
        "publication_date": publication_date,
        "views": int(views),
        "content_topic": clean(raw.get("content_topic") or raw.get("topic")) or "unspecified",
        "hook_formula": clean(raw.get("hook_formula")) or "unspecified",
        "format": clean(raw.get("format")) or "unspecified",
    }
    for field in ("reach", "shares", "saves", "follows", "average_watch_time_seconds"):
        value = strict_number(raw.get(field), field, row_number)
        if field != "average_watch_time_seconds" and value is not None and not value.is_integer():
            raise IntelligenceDataError(f"row {row_number}: {field} must be a whole count")
        result[field] = None if value is None else value
    result["three_second_retention"] = _ratio(raw.get("three_second_retention"), "three_second_retention", row_number)
    result["non_follower_reach"] = _ratio(raw.get("non_follower_reach"), "non_follower_reach", row_number)
    return result


def _metric_coverage(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    count = sum(row.get(field) is not None for row in rows)
    return {"available_posts": count, "total_posts": len(rows), "coverage": round(count / len(rows), 3) if rows else 0}


def _group_patterns(rows: list[dict[str, Any]], field: str, *, dataset_sample_size: int) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row.get(field) or "unspecified")].append(row)
    result: list[dict[str, Any]] = []
    for name, items in groups.items():
        multiples = [row["outlier_multiple"] for row in items if row.get("outlier_multiple") is not None]
        retention = [row["three_second_retention"] for row in items if row.get("three_second_retention") is not None]
        share_rates = [row["shares_per_reach"] for row in items if row.get("shares_per_reach") is not None]
        result.append({
            field: name,
            "sample_size": len(items),
            "adequate_sample": len(items) >= 3,
            "classification": "descriptive_pattern",
            "not_causal": True,
            "confidence": "low" if dataset_sample_size < 20 or len(items) < 5 else "medium",
            "median_outlier_multiple": round(float(median(multiples)), 3) if multiples else None,
            "median_three_second_retention": round(float(median(retention)), 3) if retention else None,
            "median_shares_per_reach": round(float(median(share_rates)), 5) if share_rates else None,
            "post_ids": [row["post_id"] for row in items],
        })
    return sorted(result, key=lambda row: (-(row["median_outlier_multiple"] or -1), row[field]))


def audit_posts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    validated: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    warnings: list[dict[str, Any]] = []
    for index, raw in enumerate(rows, 2):
        row = _validate_row(raw, index)
        if row["post_id"] in seen_ids:
            warnings.append({"code": "duplicate_post_ignored", "post_id": row["post_id"], "row": index})
            continue
        seen_ids.add(row["post_id"])
        validated.append(row)
    if not validated:
        raise IntelligenceDataError("audit dataset has no usable unique posts")
    account_median = median([float(row["views"]) for row in validated])
    if account_median is None or account_median <= 0:
        warnings.append({"code": "zero_account_median", "detail": "Outlier multiples and relative ranking are unavailable."})
        account_median = 0.0
    for row in validated:
        row["outlier_multiple"] = round(row["views"] / account_median, 3) if account_median > 0 else None
        reach = row.get("reach")
        row["shares_per_reach"] = round(row["shares"] / reach, 6) if reach and row.get("shares") is not None else None
        row["saves_per_reach"] = round(row["saves"] / reach, 6) if reach and row.get("saves") is not None else None
        row["follows_per_reach"] = round(row["follows"] / reach, 6) if reach and row.get("follows") is not None else None
    ranked = sorted(
        [row for row in validated if row["outlier_multiple"] is not None],
        key=lambda row: (-row["outlier_multiple"], row["post_id"]),
    )
    count = min(5, max(1, len(ranked) // 3)) if ranked else 0
    top = ranked[:count]
    bottom = list(reversed(ranked[-count:])) if count else []
    coverage = {field: _metric_coverage(validated, field) for field in OPTIONAL_NUMBERS}
    for field, values in coverage.items():
        if values["available_posts"] == 0:
            warnings.append({"code": "metric_absent", "metric": field})
        elif values["coverage"] < 0.75:
            warnings.append({"code": "metric_partial", "metric": field, "coverage": values["coverage"]})
    if len(validated) < 20:
        warnings.append({"code": "small_sample", "detail": f"Only {len(validated)} posts; conclusions are directional."})

    sample_sufficient = len(validated) >= 20
    optional_complete = all(item["coverage"] == 1 for item in coverage.values())
    confidence_ceiling = "medium" if sample_sufficient and optional_complete else "low"
    dataset_quality = {
        "sample_size": len(validated),
        "minimum_sample_for_non_exploratory_patterns": 20,
        "sample_sufficient": sample_sufficient,
        "optional_metrics_complete": optional_complete,
        "confidence_ceiling": confidence_ceiling,
        "recommendation_policy": "descriptive_and_experimental_only",
    }

    hook_patterns = _group_patterns(validated, "hook_formula", dataset_sample_size=len(validated))
    topic_patterns = _group_patterns(validated, "content_topic", dataset_sample_size=len(validated))
    descriptive_patterns: list[dict[str, Any]] = []
    for pattern_type, patterns, key in (
        ("hook_formula", hook_patterns, "hook_formula"),
        ("content_topic", topic_patterns, "content_topic"),
    ):
        for pattern in patterns:
            if pattern["adequate_sample"] and pattern["median_outlier_multiple"] is not None:
                descriptive_patterns.append({
                    "type": pattern_type,
                    "value": pattern[key],
                    "sample_size": pattern["sample_size"],
                    "median_outlier_multiple": pattern["median_outlier_multiple"],
                    "post_ids": pattern["post_ids"],
                    "classification": "descriptive_pattern",
                    "confidence": pattern["confidence"],
                    "not_causal": True,
                })

    hypotheses: list[dict[str, Any]] = []
    top_retention = [row["three_second_retention"] for row in top if row.get("three_second_retention") is not None]
    bottom_retention = [row["three_second_retention"] for row in bottom if row.get("three_second_retention") is not None]
    if len(top_retention) >= 2 and len(bottom_retention) >= 2:
        top_median, bottom_median = median(top_retention), median(bottom_retention)
        if top_median is not None and bottom_median is not None and top_median > bottom_median:
            hypotheses.append({
                "hypothesis": "Higher three-second retention may be associated with above-median views in this sample.",
                "evidence": {"top_median": round(top_median, 3), "bottom_median": round(bottom_median, 3), "top_n": len(top_retention), "bottom_n": len(bottom_retention)},
                "confidence": "low" if len(validated) < 20 else "medium",
                "not_causal": True,
            })
    best_hook = next((row for row in hook_patterns if row["adequate_sample"] and (row["median_outlier_multiple"] or 0) > 1), None)
    proposed_experiments: list[dict[str, Any]] = []
    if best_hook:
        experiment_confidence = (
            "low" if confidence_ceiling == "low" or best_hook["confidence"] == "low" else "medium"
        )
        proposed_experiments.append({
            "experiment": f"Run an owner-approved comparison using hook formula '{best_hook['hook_formula']}' against the current baseline.",
            "basis": "descriptive_pattern_not_causal",
            "sample_size": best_hook["sample_size"],
            "median_outlier_multiple": best_hook["median_outlier_multiple"],
            "confidence": experiment_confidence,
            "exploratory_only": experiment_confidence == "low",
            "requires_owner_approval": True,
            "automatic_change": False,
            "causal_claim": False,
        })
    recommendations: list[dict[str, Any]] = []
    if not sample_sufficient or not optional_complete:
        recommendations.append({
            "action": "Collect more complete per-post metrics before changing the content plan.",
            "basis": "insufficient_evidence",
            "confidence": "high",
        })
    labels = sorted({row["dataset_label"] for row in validated})
    return {
        "schema": 1,
        "module": "ig-audit-adaptation",
        "analysis_mode": "offline_import_only",
        "dataset_labels": labels,
        "sample_size": len(validated),
        "account_median_views": account_median,
        "date_range": {
            "start": min((row["publication_date"] for row in validated if row["publication_date"]), default=""),
            "end": max((row["publication_date"] for row in validated if row["publication_date"]), default=""),
        },
        "metric_coverage": coverage,
        "dataset_quality": dataset_quality,
        "observed_metrics": {
            "sample_size": len(validated),
            "account_median_views": account_median,
            "date_range": {
                "start": min((row["publication_date"] for row in validated if row["publication_date"]), default=""),
                "end": max((row["publication_date"] for row in validated if row["publication_date"]), default=""),
            },
            "metric_coverage": coverage,
        },
        "posts": validated,
        "top_posts": top,
        "bottom_posts": bottom,
        "hook_patterns": hook_patterns,
        "topic_patterns": topic_patterns,
        "descriptive_patterns": descriptive_patterns,
        "hypotheses": hypotheses,
        "proposed_experiments": proposed_experiments,
        "recommendations": recommendations,
        "warnings": warnings,
        "limitations": [
            "Only imported fields are calculated; missing reach, retention, follows or non-follower data are never inferred.",
            "The existing Buffer integration exposes publishing/status data, not a documented complete Instagram Insights feed.",
            "Observed associations are separated from hypotheses and do not prove causation.",
        ],
    }
