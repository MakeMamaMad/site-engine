"""Generate deterministic old/new Growth Agent comparison artifacts.

This script never imports a publisher and never calls a paid API.  It is safe
to run against production-shaped news data because it only writes previews.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


AUTPOSTER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = AUTPOSTER_ROOT.parents[1]
if str(AUTPOSTER_ROOT) not in sys.path:
    sys.path.insert(0, str(AUTPOSTER_ROOT))

from src.ai.growth_agent import (  # noqa: E402
    GrowthAgentError,
    build_fallback_storyboard,
    growth_report,
    recommend_content_plan,
)
from src.ai.storyboard import fallback_storyboard  # noqa: E402


CATEGORIES = {
    "commercial_news": ("грузовик", "тягач", "полуприцеп", "прицеп", "автобус", "шасси", "фургон"),
    "regulation_logistics": ("закон", "штраф", "регламент", "пошлин", "перевоз", "логист", "рынок"),
    "technical_practical": ("обслужив", "ремонт", "шины", "пробег", "ось", "двигател", "расход"),
}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _category_score(item: dict[str, Any], category: str, markers: tuple[str, ...]) -> int:
    title = _clean(item.get("title")).lower()
    summary = _clean(item.get("summary")).lower()
    combined = f"{title} {summary}"
    score = 4 * sum(marker in title for marker in markers) + sum(marker in summary for marker in markers)
    if category in {"commercial_news", "technical_practical"}:
        score += 3 * sum(
            marker in combined for marker in ("грузов", "прицеп", "тягач", "автопарк", "коммерческ")
        )
    if category == "commercial_news":
        score += 6 * sum(
            marker in title for marker in ("представ", "выпуст", "запуст", "показал", "новин", "новый", "новая")
        )
    if category == "technical_practical":
        score += 4 * sum(
            marker in combined for marker in ("обслужив", "ремонт", "провер", "интервал", "шины", "пробег")
        )
    if category == "regulation_logistics":
        score += 6 * sum(
            marker in combined for marker in ("закон", "штраф", "пошлин", "регламент", "постановлен", "норм")
        )
    if "<figure" in summary:
        score -= 3
    if "телефон" in summary:
        score -= 6
    if "впервые появ" in summary:
        score -= 20 if category == "regulation_logistics" else 3
    return score


def _select(items: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    used: set[str] = set()
    selected: list[tuple[str, dict[str, Any]]] = []
    for category, markers in CATEGORIES.items():
        ranked = sorted(
            items,
            key=lambda item: _category_score(item, category, markers),
            reverse=True,
        )
        for item in ranked:
            key = str(item.get("id") or item.get("slug"))
            if key in used:
                continue
            candidate = dict(item)
            if candidate.get("slug"):
                candidate["site_url"] = f"https://spec-avtoportal.ru/news/{candidate['slug']}/"
            try:
                build_fallback_storyboard(candidate)
            except GrowthAgentError:
                continue
            selected.append((category, candidate))
            used.add(key)
            break
    return selected


def _captions(board: Any) -> str:
    return (
        "## Instagram\n\n" + board.instagram_caption +
        "\n\n## TikTok\n\n" + board.tiktok_caption +
        "\n\n## YouTube Shorts\n\n" + board.youtube_description + "\n"
    )


def generate(news_path: Path, state_path: Path, output: Path) -> None:
    raw = json.loads(news_path.read_text(encoding="utf-8"))
    items = raw.get("items", []) if isinstance(raw, dict) else raw
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    previous_titles = [row.get("title", "") for row in state.get("renders", []) if isinstance(row, dict)]
    output.mkdir(parents=True, exist_ok=True)
    recent_items = [item for item in items[:200] if isinstance(item, dict)]
    cases = _select(recent_items)
    if len(cases) < 3:
        raise RuntimeError("Could not find three grounded preview cases")
    index: list[dict[str, Any]] = []
    for category, item in cases:
        case_dir = output / category
        case_dir.mkdir(parents=True, exist_ok=True)
        original = fallback_storyboard(item)
        improved = build_fallback_storyboard(item, reason="offline preview; paid AI disabled")
        source_snapshot = {
            key: item.get(key)
            for key in ("id", "slug", "title", "summary", "source", "link", "site_url", "tags", "published_at")
            if item.get(key) not in (None, "", [])
        }
        (case_dir / "source_item.json").write_text(
            json.dumps(source_snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (case_dir / "original_storyboard.json").write_text(json.dumps(original.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        (case_dir / "growth_storyboard.json").write_text(json.dumps(improved.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        (case_dir / "original_captions.md").write_text(_captions(original), encoding="utf-8")
        (case_dir / "improved_captions.md").write_text(_captions(improved), encoding="utf-8")
        (case_dir / "quality_report.json").write_text(json.dumps(growth_report(improved), ensure_ascii=False, indent=2), encoding="utf-8")
        index.append({"category": category, "id": item.get("id"), "title": item.get("title"), "directory": category})
    plan = recommend_content_plan(items[:200], previous_titles[-20:], limit=7)
    (output / "content_plan_recommendation.json").write_text(json.dumps({"scheduling_effect": "none", "items": plan}, ensure_ascii=False, indent=2), encoding="utf-8")
    readme = (
        "# Instagram Growth Agent v1 preview\n\n"
        "These three comparisons use the same source item on both sides. The original side uses the existing deterministic storyboard; "
        "the Growth Agent side uses the offline source-grounded engine. No publisher is imported or called.\n\n"
        "MP4 files are not included in this local run because FFmpeg is unavailable on the Windows host. The storyboard, captions and "
        "validation reports are complete; the existing CI preview workflow can render MP4 with the same voice and visual settings.\n\n"
        "Cases:\n" + "".join(f"- `{row['category']}` — {row['title']}\n" for row in index) +
        "\n`content_plan_recommendation.json` is advisory only and does not change the publication schedule.\n"
    )
    (output / "README.md").write_text(readme, encoding="utf-8")
    (output / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--news", type=Path, default=REPO_ROOT / "frontend" / "data" / "news.json")
    parser.add_argument("--state", type=Path, default=AUTPOSTER_ROOT / "state" / "v2.json")
    parser.add_argument("--output", type=Path, default=AUTPOSTER_ROOT / "previews" / "growth_agent_v1")
    args = parser.parse_args()
    generate(args.news, args.state, args.output)
    print(f"Growth Agent preview written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
