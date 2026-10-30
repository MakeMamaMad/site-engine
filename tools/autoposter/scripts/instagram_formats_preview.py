"""Generate deterministic, nonpublishing profile/carousel/Stories review artifacts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


AUTPOSTER_ROOT = Path(__file__).resolve().parents[1]
if str(AUTPOSTER_ROOT) not in sys.path:
    sys.path.insert(0, str(AUTPOSTER_ROOT))

from src.formats.pipeline import build_formats_preview  # noqa: E402
from src.intelligence.common import read_json, write_json  # noqa: E402


PROFILE_FIXTURE = AUTPOSTER_ROOT / "tests" / "fixtures" / "instagram_formats" / "profile_fixture.json"
EDITORIAL_EVIDENCE = AUTPOSTER_ROOT / "tests" / "fixtures" / "instagram_formats" / "bpw_editorial_evidence.json"
ARTICLE_SNAPSHOT = AUTPOSTER_ROOT / "previews" / "growth_agent_v1" / "technical_practical" / "source_item.json"


def _profile_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Instagram profile audit — synthetic fixture",
        "",
        "> This profile snapshot is fabricated test data, not a verified live account audit. Nothing was changed on Instagram.",
        "",
        f"Status: **{report['verification_status']}**. Indicative score: **{report['total_score']}/100**. "
        "The score is not fully verified while important visual/activity inputs are absent.",
        "",
        "| Criterion | Score | Finding | Verified? |",
        "|---|---:|---|---|",
    ]
    for row in report["criteria"]:
        lines.append(f"| {row['criterion']} | {row['score']}/{row['maximum']} | {row['finding']} | {'yes' if row['verified'] else 'no'} |")
    lines += ["", "## Before", "", f"- Name: {report['current_copy']['profile_name']}", f"- Bio: {report['current_copy']['bio']}", f"- Link: {report['current_copy']['website_link']}", "", "## Proposed profile names", ""]
    lines.extend(f"- {row['text']} ({row['characters']}/{row['limit']})" for row in report["proposed_copy"]["profile_names"])
    lines += ["", "## Proposed bios", ""]
    lines.extend(f"- {row['text']} ({row['characters']}/{row['limit']})" for row in report["proposed_copy"]["bios"])
    lines += ["", "## Pinned-post strategy", ""]
    lines.extend(f"- Slot {row['slot']} · **{row['job']}** — {row['recommendation']}" for row in report["pinned_strategy"])
    lines += ["", "## Highlights", "", " → ".join(report["highlight_recommendations"])]
    lines += ["", "## Grid-cover rules", ""]
    lines.extend(f"- {value}" for value in report["grid_cover_suggestions"])
    lines += ["", "## Missing-data warnings", ""]
    lines.extend(f"- `{row['code']}` — {row.get('field') or ', '.join(row.get('criteria', []))}" for row in report["missing_data_warnings"])
    lines += ["", "## Conversion path", "", f"{report['website_conversion_path']['path']} → {report['website_conversion_path']['destination']}", "", "Owner must verify the live edit-screen limits and all missing profile inputs before applying any copy.", ""]
    return "\n".join(lines)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _before_after(carousel: dict[str, Any], stories: dict[str, Any]) -> str:
    lines = [
        "# Editorial copy comparison",
        "",
        "## Carousel",
        "",
        "Before: generic headings such as `ПОЧЕМУ ЭТО ВАЖНО`, `КЛЮЧЕВОЙ ФАКТ` and full source sentences used as body copy.",
        "",
        "After:",
        "",
    ]
    lines.extend(f"- **{row['headline']}** — {row['body']}" for row in carousel["slides"])
    lines += [
        "", "## Stories", "",
        "Before: the same source paragraphs and generic labels were reused from the carousel.",
        "", "After: conversational, independently mapped Story copy:", "",
    ]
    lines.extend(f"- **{row['headline']}** — {row['body']}" for row in stories["frames"])
    lines += ["", "Every shortened factual line is tied to an explicit reviewed mapping and original-source evidence.", ""]
    return "\n".join(lines)


def generate(profile_path: Path, article_path: Path, evidence_path: Path, output: Path) -> dict[str, Any]:
    profile = read_json(profile_path)
    source = read_json(article_path)
    editorial_evidence = read_json(evidence_path)
    source["data_classification"] = "repository_owned_article_snapshot"
    source["editorial_evidence"] = editorial_evidence
    report = build_formats_preview(profile=profile, source=source, output_dir=output, enabled=True)
    profile_report = report["profile"]
    carousel = report["carousel"]["package"]
    stories = report["stories"]["package"]
    write_json(output / "profile_audit.json", profile_report)
    _write_text(output / "profile_audit.md", _profile_markdown(profile_report))
    write_json(output / "carousel" / "manifest.json", carousel)
    write_json(output / "carousel" / "attribution.json", carousel["attribution_manifest"])
    write_json(output / "carousel" / "visual_qa.json", report["carousel"]["render"]["qa"])
    _write_text(output / "carousel" / "caption.md", carousel["caption"] + "\n")
    _write_text(output / "carousel" / "alt_text.md", "\n\n".join(f"{row['counter']} — {row['alt_text']}" for row in carousel["slides"]) + "\n")
    write_json(output / "stories" / "manifest.json", stories)
    write_json(output / "stories" / "attribution.json", stories["attribution_manifest"])
    write_json(output / "stories" / "visual_qa.json", report["stories"]["render"]["qa"])
    _write_text(output / "stories" / "alt_text.md", "\n\n".join(f"{row['counter']} — {row['alt_text']}" for row in stories["frames"]) + "\n")
    factual_checks = []
    for container, items in (("carousel", carousel["slides"]), ("stories", stories["frames"])):
        for item in items:
            for evidence in item.get("evidence") or []:
                factual_checks.append({
                    "format": container,
                    "number": item["number"],
                    "supported": item["factual_validation"]["supported"],
                    "source_url": evidence["source_url"],
                    "original_text": evidence["original_text"],
                    "russian_translation": evidence["russian_translation"],
                })
    write_json(output / "factual_qa.json", {
        "source_classification": source["data_classification"],
        "source_url": source["site_url"],
        "original_source_url": source.get("link") or "",
        "checks": factual_checks,
        "all_evidence_supported": all(row["supported"] for row in factual_checks),
        "manufacturer_model_rewrites_allowed": False,
        "unsupported_facts_added": False,
    })
    write_json(output / "source_evidence.json", editorial_evidence)
    _write_text(output / "before_after_copy.md", _before_after(carousel, stories))
    write_json(output / "safety_manifest.json", {
        key: report[key] for key in (
            "enabled", "advisory_only", "publishing_invoked", "profile_modified",
            "messages_sent", "scheduling_effect", "production_state_changed",
        )
    })
    _write_text(output / "README.md", (
        "# Instagram formats demonstration\n\n"
        "The profile is an explicitly synthetic fixture. Carousel and Stories copy is extracted from the existing repository-owned BPW article snapshot. "
        "Concise visible copy uses explicit reviewed mappings to original-source evidence; hub cap is retained in the terminology manifest and rendered as крышка ступицы. "
        "No external image is used: the previews contain only SpecAvtoPortal brand graphics, source-grounded text, and attribution. "
        "The link sticker is a manual placement instruction and is not visually simulated as functional. Nothing was published or changed in production.\n"
    ))
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", type=Path, default=PROFILE_FIXTURE)
    parser.add_argument("--article", type=Path, default=ARTICLE_SNAPSHOT)
    parser.add_argument("--evidence", type=Path, default=EDITORIAL_EVIDENCE)
    parser.add_argument("--output", type=Path, default=AUTPOSTER_ROOT / "previews" / "instagram_formats")
    args = parser.parse_args()
    generate(args.profile, args.article, args.evidence, args.output)
    print(f"Instagram format previews written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
