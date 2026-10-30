"""Generate deterministic old/new Growth Agent comparison artifacts.

This script never calls a publisher or a paid API. It is safe to run against
production-shaped news data because it only writes previews.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


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
from src.ai.visuals import generate_scene_visual  # noqa: E402
from src.render.short_v2 import render_short  # noqa: E402
from src.v2_main import generate_scene_voice_track  # noqa: E402


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


def _probe(path: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_streams", "-show_format",
            "-of", "json", str(path),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    raw = json.loads(proc.stdout)
    streams = raw.get("streams", [])
    video = next((row for row in streams if row.get("codec_type") == "video"), {})
    audio = next((row for row in streams if row.get("codec_type") == "audio"), {})
    return {
        "duration_seconds": round(float(raw.get("format", {}).get("duration") or 0), 3),
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "video_codec": video.get("codec_name", ""),
        "audio_codec": audio.get("codec_name", ""),
        "has_video": bool(video),
        "has_audio": bool(audio),
    }


def _perceptual_key(path: Path) -> str:
    with Image.open(path) as source:
        image = source.convert("L").resize((16, 16))
    pixels = list(image.getdata())
    average = sum(pixels) / max(1, len(pixels))
    return "".join("1" if value >= average else "0" for value in pixels)


def _supporting_copy_visible(path: Path) -> bool:
    with Image.open(path) as source:
        image = source.convert("L")
        crop = image.crop((48, 1320, image.width - 48, 1720))
    # The renderer puts pale supporting copy on a dark panel in this zone.
    return sum(value >= 205 for value in crop.getdata()) >= 450


def _orange_cta_visible(path: Path) -> bool:
    with Image.open(path) as source:
        image = source.convert("RGB")
    return sum(r > 210 and 45 < g < 145 and b < 45 for r, g, b in image.getdata()) >= 1200


def _contact_sheet(frames: list[Path], output: Path) -> None:
    thumb_size = (270, 480)
    columns = min(3, len(frames))
    rows = (len(frames) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * thumb_size[0], rows * (thumb_size[1] + 34)), (15, 18, 22))
    draw = ImageDraw.Draw(sheet)
    for index, frame in enumerate(frames):
        with Image.open(frame) as source:
            thumb = source.convert("RGB").resize(thumb_size)
        x = (index % columns) * thumb_size[0]
        y = (index // columns) * (thumb_size[1] + 34)
        sheet.paste(thumb, (x, y))
        draw.text((x + 10, y + thumb_size[1] + 8), f"scene {index + 1}", fill=(246, 247, 249))
    sheet.save(output, "PNG", optimize=True)


def _render_variant(board: Any, variant_dir: Path, variant: str) -> dict[str, Any]:
    variant_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"growth-{variant}-") as tmp:
        work = Path(tmp)
        visuals: list[Path] = []
        visual_modes: list[str] = []
        for index, scene in enumerate(board.scenes, 1):
            visual = work / "visuals" / f"scene_{index:02d}.png"
            visual_modes.append(generate_scene_visual(scene, visual))
            visuals.append(visual)
        voice, scene_audio_seconds, tts_mode = generate_scene_voice_track(board, work)
        video = variant_dir / f"{variant}.mp4"
        render_info = render_short(
            board,
            visuals,
            voice,
            video,
            work / "render",
            scene_audio_seconds=scene_audio_seconds,
        )
        frames = sorted((work / "render" / "frames").glob("scene_*.png"))
        shutil.copy2(frames[0], variant_dir / f"{variant}_first_frame.png")
        shutil.copy2(frames[-1], variant_dir / f"{variant}_final_frame.png")
        _contact_sheet(frames, variant_dir / f"{variant}_contact_sheet.png")
        probe = _probe(video)
        unique_frames = len({_perceptual_key(frame) for frame in frames})
        audio_delta = abs(float(render_info["audio_seconds"]) - probe["duration_seconds"])
        qa = {
            "variant": variant,
            "file": video.name,
            "ffprobe": probe,
            "tts_mode": tts_mode,
            "visual_modes": visual_modes,
            "scene_count": len(board.scenes),
            "duration_seconds": probe["duration_seconds"],
            "audio_sync_delta_seconds": round(audio_delta, 3),
            "resolution_ok": probe["width"] == 1080 and probe["height"] == 1920,
            "audio_present": probe["has_audio"],
            "audio_sync_ok": audio_delta <= 0.35,
            "supporting_copy_visible": all(_supporting_copy_visible(frame) for frame in frames[:-1]),
            "first_scene_seconds": round(float(render_info["durations"][0]), 3),
            "first_three_seconds_ok": (
                float(render_info["durations"][0]) <= 3.15
                and board.scenes[0].overlay == board.hook
            ),
            "transition_count": max(0, len(board.scenes) - 1),
            "transitions_ok": len(frames) == len(board.scenes) and len(board.scenes) > 1,
            "unique_scene_frames": unique_frames,
            "visual_diversity_ok": unique_frames >= min(3, len(frames)),
            "final_cta_ok": board.scenes[-1].id.startswith("cta") and _orange_cta_visible(frames[-1]),
        }
        return qa


def generate(news_path: Path, state_path: Path, output: Path, *, render: bool = False) -> None:
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
        comparison_qa: dict[str, Any] | None = None
        if render:
            original_qa = _render_variant(original, case_dir, "original")
            growth_qa = _render_variant(improved, case_dir, "growth")
            comparison_qa = {
                "source_id": item.get("id"),
                "source_title": item.get("title"),
                "matching_settings": {
                    "voice": os.getenv("VOICE", "ru-RU-DmitryNeural"),
                    "tts_rate": os.getenv("TTS_RATE", "+8%"),
                    "natural_voice_enabled": os.getenv("NATURAL_VOICE_ENABLED", "0"),
                    "natural_voice_profile": os.getenv("NATURAL_VOICE_PROFILE", ""),
                    "ai_images": os.getenv("AI_IMAGES", "0"),
                    "width": 1080,
                    "height": 1920,
                    "fps": 30,
                },
                "original": original_qa,
                "growth": growth_qa,
            }
            (case_dir / "video_qa.json").write_text(
                json.dumps(comparison_qa, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            required = (
                "resolution_ok", "audio_present", "audio_sync_ok", "supporting_copy_visible",
                "first_three_seconds_ok", "transitions_ok", "visual_diversity_ok", "final_cta_ok",
            )
            failed = [key for key in required if not growth_qa[key]]
            if failed:
                raise RuntimeError(f"Growth video QA failed for {category}: {failed}")
        index.append({
            "category": category,
            "id": item.get("id"),
            "title": item.get("title"),
            "directory": category,
            "rendered": render,
            "qa": comparison_qa,
        })
    plan = recommend_content_plan(items[:200], previous_titles[-20:], limit=7)
    (output / "content_plan_recommendation.json").write_text(json.dumps({"scheduling_effect": "none", "items": plan}, ensure_ascii=False, indent=2), encoding="utf-8")
    readme = (
        "# Instagram Growth Agent v1 preview\n\n"
        "These three comparisons use the same source item on both sides. The original side uses the existing deterministic storyboard; "
        "the Growth Agent side uses the offline source-grounded engine. No publisher function is called.\n\n"
        + (
            "Each case includes `original.mp4` and `growth.mp4`, ffprobe/QA results, first/final frames and contact sheets. "
            "Both variants use the same voice, render size, frame rate and image mode.\n\n"
            if render else
            "This metadata-only run omitted MP4 rendering. Run with `--render` on a host with FFmpeg/ffprobe.\n\n"
        ) +
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
    parser.add_argument("--render", action="store_true", help="Render old/new MP4s and run ffprobe/visual QA")
    args = parser.parse_args()
    os.environ.setdefault("AI_IMAGES", "0")
    os.environ.setdefault("OPENAI_TTS", "0")
    os.environ.setdefault("TTS_ENGINE", "edge")
    os.environ.setdefault("ALLOW_PAID_TTS", "0")
    generate(args.news, args.state, args.output, render=args.render)
    print(f"Growth Agent preview written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
