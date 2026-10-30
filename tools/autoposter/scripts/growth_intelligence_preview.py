"""Generate deterministic, read-only Growth Intelligence demonstration reports."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


AUTPOSTER_ROOT = Path(__file__).resolve().parents[1]
if str(AUTPOSTER_ROOT) not in sys.path:
    sys.path.insert(0, str(AUTPOSTER_ROOT))

from src.intelligence.audit import audit_posts, load_audit_rows  # noqa: E402
from src.intelligence.common import read_json, write_json  # noqa: E402
from src.intelligence.pipeline import build_recommendation_pipeline  # noqa: E402
from src.intelligence.repurpose import build_repurposing_package  # noqa: E402
from src.intelligence.viral import analyze_viral_patterns, load_viral_rows  # noqa: E402


FIXTURES = AUTPOSTER_ROOT / "tests" / "fixtures" / "growth_intelligence"


def _cell(value: Any) -> str:
    return str(value if value is not None else "—").replace("|", "\\|").replace("\n", " ")


def viral_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Viral-pattern report — synthetic fixture",
        "",
        "> These are explicitly synthetic examples, not real competitor performance or automatically collected Instagram data.",
        "",
        f"Sample: **{report['sample_size']} examples across {report['account_count']} accounts**. Baseline: {report['baseline']}.",
        "",
        "| Formula | n | Accounts | Median multiple | Top third | Adequate? |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in report["patterns"]:
        lines.append(
            f"| {_cell(row['hook_formula_name'])} | {row['sample_size']} | {row['account_count']} | "
            f"{row['median_outlier_multiple']:.2f}x | {row['top_third_count']} | {'yes' if row['adequate_sample'] else 'no'} |"
        )
    lines += ["", "## Original Russian recommendations", ""]
    for row in report["recommendations"]:
        evidence = row["evidence"]
        lines.append(
            f"- **{row['hook_formula']}** — {row['russian_hook_template']} "
            f"(n={evidence['sample_size']}, {evidence['account_count']} accounts, median {evidence['median_outlier_multiple']:.2f}x)."
        )
    lines += ["", "## Data warnings", ""]
    if report["warnings"]:
        lines.extend(f"- `{row['code']}` — {_cell(row.get('detail') or row)}" for row in report["warnings"])
    else:
        lines.append("- None.")
    lines += ["", "Source URLs and account baselines are retained in `viral_pattern_report.json`. No scraping or login was used.", ""]
    return "\n".join(lines)


def repurpose_markdown(report: dict[str, Any]) -> str:
    extraction = report["extraction"]
    counts = extraction["counts"]
    lines = [
        "# Repurposing package — representative transport fixture",
        "",
        "> The source is a synthetic representative fixture. It is not presented as a real published performance result.",
        "",
        f"Source: [{report['source']['title']}]({report['source']['source_url']})",
        "",
        f"Extracted: **{counts['claims']} claims**, **{counts['numbers_and_specifications']} specifications**, "
        f"**{counts['mechanisms']} mechanisms**, **{counts['practical_recommendations']} practical points**, "
        f"**{counts['quotable_statements']} quotes**.",
        "",
        "## Reel concepts",
        "",
    ]
    for concept in report["reel_concepts"]:
        lines += [
            f"### {concept['angle']}",
            f"- Hook: {concept['suggested_hook']}",
            f"- Claim: {concept['core_claim']}",
            f"- Exact evidence: {concept['source_evidence'][0]['exact_text']}",
            f"- Validation: {'supported' if concept['factual_validation']['supported'] else 'rejected'}",
            "",
        ]
    lines += ["## Carousel outlines", ""]
    for carousel in report["carousel_outlines"]:
        lines.append(f"- **{carousel['title']}** — {len(carousel['slides'])} slides; every evidence slide retains the source URL.")
    lines += ["", "## Story concepts", ""]
    for story in report["story_concepts"]:
        lines.append(f"- **{story['type']}** — {story['text']}")
    lines += ["", "Advisory only: no schedule or publisher was called.", ""]
    return "\n".join(lines)


def audit_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Instagram analytics audit — synthetic fixture",
        "",
        "> All metrics in this report are synthetic test data, not real SpecAvtoPortal audience performance.",
        "",
        f"Posts: **{report['sample_size']}**. Median views: **{report['account_median_views']:.0f}**. "
        f"Range: {report['date_range']['start']} to {report['date_range']['end']}.",
        "",
        "## Top posts relative to the account median",
        "",
        "| Post | Multiple | Views | Reach | 3s retention | Shares/reach |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in report["top_posts"]:
        retention = f"{row['three_second_retention']:.0%}" if row.get("three_second_retention") is not None else "—"
        share_rate = f"{row['shares_per_reach']:.2%}" if row.get("shares_per_reach") is not None else "—"
        lines.append(f"| {row['post_id']} | {row['outlier_multiple']:.2f}x | {row['views']} | {_cell(row['reach'])} | {retention} | {share_rate} |")
    lines += ["", "## Observed metrics", ""]
    lines.append(
        f"- Imported posts: {report['observed_metrics']['sample_size']}; "
        f"median views: {report['observed_metrics']['account_median_views']:.0f}."
    )
    lines += ["", "## Descriptive patterns — not causal findings", ""]
    for fact in report["descriptive_patterns"]:
        lines.append(
            f"- {fact['type']} **{fact['value']}**: median {fact['median_outlier_multiple']:.2f}x, n={fact['sample_size']}."
        )
    lines += ["", "## Hypotheses — not causal findings", ""]
    if report["hypotheses"]:
        lines.extend(f"- {row['hypothesis']} Confidence: {row['confidence']}." for row in report["hypotheses"])
    else:
        lines.append("- None supported by the available fields.")
    lines += ["", "## Proposed experiments", ""]
    if report["proposed_experiments"]:
        for row in report["proposed_experiments"]:
            lines.append(
                f"- {row['experiment']} Confidence ceiling: {row['confidence']}; "
                f"exploratory only: {'yes' if row['exploratory_only'] else 'no'}."
            )
    else:
        lines.append("- None; collect more evidence first.")
    lines += ["", "## Missing/partial data warnings", ""]
    if report["warnings"]:
        lines.extend(f"- `{row['code']}` — {_cell(row.get('metric') or row.get('detail') or row)}" for row in report["warnings"])
    else:
        lines.append("- None.")
    lines += ["", "No missing reach, retention, follows or non-follower metrics were inferred.", ""]
    return "\n".join(lines)


def generate(viral_path: Path, article_path: Path, audit_path: Path, output: Path) -> None:
    viral_rows = load_viral_rows(viral_path)
    source = read_json(article_path)
    audit_rows = load_audit_rows(audit_path)
    viral = analyze_viral_patterns(viral_rows)
    repurpose = build_repurposing_package(source)
    audit = audit_posts(audit_rows)
    pipeline = build_recommendation_pipeline(
        viral_rows=viral_rows,
        source=source,
        audit_rows=audit_rows,
        enabled=True,
    )
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "viral_pattern_report.json", viral)
    write_json(output / "repurposing_package.json", repurpose)
    write_json(output / "analytics_audit_report.json", audit)
    write_json(output / "recommendation_pipeline.json", pipeline)
    (output / "viral_pattern_report.md").write_text(viral_markdown(viral), encoding="utf-8")
    (output / "repurposing_package.md").write_text(repurpose_markdown(repurpose), encoding="utf-8")
    (output / "analytics_audit_report.md").write_text(audit_markdown(audit), encoding="utf-8")
    (output / "README.md").write_text(
        "# Growth Intelligence demonstration\n\n"
        "All competitor and audience metrics are synthetic fixtures and are not real performance. "
        "The article is a synthetic representative transport source. The pipeline is read-only: "
        "it changes no schedule, topic weight, publication state or external account.\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--viral", type=Path, default=FIXTURES / "viral_examples.csv")
    parser.add_argument("--article", type=Path, default=FIXTURES / "transport_article.json")
    parser.add_argument("--audit", type=Path, default=FIXTURES / "audit_posts.json")
    parser.add_argument("--output", type=Path, default=AUTPOSTER_ROOT / "previews" / "growth_intelligence")
    args = parser.parse_args()
    generate(args.viral, args.article, args.audit, args.output)
    print(f"Growth Intelligence reports written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
