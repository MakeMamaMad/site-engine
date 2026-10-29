"""Read-only connection of viral evidence, owned metrics and source ideas."""
from __future__ import annotations

import os
from typing import Any

from .audit import audit_posts
from .repurpose import build_repurposing_package
from .viral import analyze_viral_patterns, classify_hook_formula


def is_enabled(value: str | None = None) -> bool:
    if value is None:
        value = os.getenv("GROWTH_INTELLIGENCE_ENABLED", "0")
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def build_recommendation_pipeline(
    *,
    viral_rows: list[dict[str, Any]],
    source: dict[str, Any],
    audit_rows: list[dict[str, Any]],
    enabled: bool | None = None,
) -> dict[str, Any]:
    active = is_enabled() if enabled is None else bool(enabled)
    if not active:
        return {
            "schema": 1,
            "enabled": False,
            "status": "disabled",
            "advisory_only": True,
            "production_topic_weights_changed": False,
            "content_plan_suggestions": [],
        }
    viral = analyze_viral_patterns(viral_rows)
    repurpose = build_repurposing_package(source)
    audit = audit_posts(audit_rows)
    viral_formulas = [row["hook_formula"] for row in viral["recommendations"]]
    audit_formulas = [
        row["hook_formula"] for row in audit["hook_patterns"]
        if row["adequate_sample"] and (row["median_outlier_multiple"] or 0) >= 1
    ]
    shared = [formula for formula in viral_formulas if formula in audit_formulas]
    preferred = shared or audit_formulas or viral_formulas
    suggestions: list[dict[str, Any]] = []
    for index, concept in enumerate(repurpose.get("reel_concepts", [])):
        concept_formula, _ = classify_hook_formula(concept["suggested_hook"])
        formula = concept_formula if concept_formula != "unclassified" else "source_fact_first"
        experiment_formula = preferred[index % len(preferred)] if preferred else None
        viral_pattern = next((row for row in viral["patterns"] if row["hook_formula"] == formula), None)
        audit_pattern = next((row for row in audit["hook_patterns"] if row["hook_formula"] == formula), None)
        suggestions.append({
            "format": "reel",
            "angle": concept["angle"],
            "suggested_hook": concept["suggested_hook"],
            "recommended_hook_formula": formula,
            "evidence_based_pattern_experiment": ({
                "hook_formula": experiment_formula,
                "requires_editorial_rewrite": experiment_formula != formula,
                "constraint": "Any rewrite must retain the exact source claim and pass factual validation.",
            } if experiment_formula else None),
            "source_evidence": concept["source_evidence"],
            "evidence": {
                "competitor_fixture_pattern": ({
                    "sample_size": viral_pattern["sample_size"],
                    "account_count": viral_pattern["account_count"],
                    "median_outlier_multiple": viral_pattern["median_outlier_multiple"],
                } if viral_pattern else None),
                "owned_metrics_pattern": ({
                    "sample_size": audit_pattern["sample_size"],
                    "median_outlier_multiple": audit_pattern["median_outlier_multiple"],
                } if audit_pattern else None),
            },
            "confidence": "medium" if formula in shared else "source_grounded_only",
            "approval_required": True,
        })
    for carousel in repurpose.get("carousel_outlines", []):
        suggestions.append({
            "format": "carousel",
            "angle": "source_mechanism_or_specifications",
            "title": carousel["title"],
            "source_evidence": carousel["source_evidence"],
            "confidence": "source_grounded",
            "approval_required": True,
        })
    return {
        "schema": 1,
        "enabled": True,
        "status": "advisory_ready" if suggestions else "insufficient_evidence",
        "advisory_only": True,
        "publishing_invoked": False,
        "scheduling_effect": "none",
        "production_topic_weights_changed": False,
        "data_classification": {
            "viral": viral["dataset_labels"],
            "audit": audit["dataset_labels"],
            "source": repurpose["source"]["data_classification"],
        },
        "evidence_summary": {
            "viral_examples": viral["sample_size"],
            "viral_accounts": viral["account_count"],
            "audited_posts": audit["sample_size"],
            "source_claims": repurpose["extraction"]["counts"]["claims"],
            "shared_supported_formulas": shared,
        },
        "content_plan_suggestions": suggestions,
        "component_status": {
            "viral": "ready",
            "repurpose": repurpose["status"],
            "audit": "ready",
        },
        "warnings": {
            "viral": viral["warnings"],
            "repurpose": repurpose["warnings"],
            "audit": audit["warnings"],
        },
        "owner_approval_required_for": [
            "using a recommendation in production",
            "connecting any new analytics source",
            "changing topic-selection weights",
            "scheduling or publishing content",
        ],
    }
