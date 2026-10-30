"""Generate deterministic Cross-Platform Growth v1 preview reports.

Outputs (all advisory, nothing is published):
- cross_platform_report.{json,md}  — synthetic three-platform fixture;
- platform_packages.{json,md}      — YouTube/Instagram/TikTok packaging for one article;
- visual_qa_report.json + contact_sheet.jpg               — renderer output (short_v2, synthetic visual);
- visual_qa_defect_report.json + contact_sheet_defect.jpg — same video with a black opening + overlong title;
- index.json                        — summary and safety confirmation.

Videos are rendered into a temporary directory and are not kept.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw


AUTPOSTER_ROOT = Path(__file__).resolve().parents[1]
if str(AUTPOSTER_ROOT) not in sys.path:
    sys.path.insert(0, str(AUTPOSTER_ROOT))

from src.crossplatform.analytics import (  # noqa: E402
    OWNER_BASELINE_SNAPSHOT,
    build_cross_platform_report,
    ingest_observations,
    load_observation_rows,
    report_markdown,
)
from src.crossplatform.hooks import build_platform_packages, packages_markdown  # noqa: E402
from src.intelligence.common import read_json, write_json  # noqa: E402


FIXTURES = AUTPOSTER_ROOT / "tests" / "fixtures" / "cross_platform"
GOOD_OVERLAYS = ["На М-5 «Урал» асфальтируют эстакаду", "1060 метров и 27 пролётов", "spec-avtoportal.ru"]
OVERLONG_OVERLAY = (
    "На трассе М-5 «Урал» начали асфальтировать самую длинную эстакаду Челябинской области "
    "в рамках реконструкции и строительства обхода Сима, работы завершат до конца года"
)


def synthetic_visual(path: Path, seed: int) -> Path:
    """Dark, detailed procedural background (no real imagery)."""
    image = Image.new("RGB", (1080, 1920), (14, 16, 20))
    draw = ImageDraw.Draw(image)
    for y in range(0, 1920, 6):
        shade = 18 + int(22 * (y / 1920)) + (seed * 7) % 13
        draw.line((0, y, 1080, y), fill=(shade, shade + 3, shade + 8))
    for i in range(26):
        x = (i * 97 + seed * 53) % 1080
        y = 300 + (i * 151 + seed * 31) % 1300
        draw.rectangle((x, y, x + 140 + (i % 4) * 40, y + 18 + (i % 3) * 10), fill=(60 + i % 5 * 9, 66, 74))
    draw.ellipse((640 - seed * 40, 420, 980 - seed * 40, 760), outline=(255, 107, 0), width=10)
    image.save(path)
    return path


def render_sample_video(work: Path) -> tuple[Path, list[str]]:
    from src.ai.storyboard import Scene, Storyboard
    from src.render.short_v2 import render_short

    scenes = [
        Scene(id=f"s{i}", seconds=3.0, overlay=text, narration="Синтетический кадр для визуальной проверки.", visual_prompt="")
        for i, text in enumerate(GOOD_OVERLAYS, 1)
    ]
    storyboard = Storyboard(version=2, format="news", title="preview", hook="", voiceover="", instagram_caption="",
                            tiktok_caption="", youtube_title="", youtube_description="", hashtags=[], source_urls=[], scenes=scenes)
    visuals = [synthetic_visual(work / f"visual_{i}.png", i) for i in range(len(scenes))]
    audio = work / "silence.m4a"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "8.0",
                    "-c:a", "aac", str(audio)], check=True)
    video = work / "sample.mp4"
    render_short(storyboard, visuals, audio, video, work / "render", platform="instagram")
    return video, GOOD_OVERLAYS


def make_defect_video(good: Path, work: Path) -> Path:
    defect = work / "defect.mp4"
    subprocess.run([
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-t", "1.2", "-i", "color=c=black:s=1080x1920:r=30",
        "-i", str(good),
        "-filter_complex", "[0:v]format=yuv420p[b];[1:v]format=yuv420p[g];[b][g]concat=n=2:v=1:a=0[v]",
        "-map", "[v]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", str(defect),
    ], check=True)
    return defect


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--skip-video", action="store_true", help="Skip rendering/visual QA (no ffmpeg needed).")
    args = parser.parse_args()
    out: Path = args.output
    out.mkdir(parents=True, exist_ok=True)

    ingested = ingest_observations(load_observation_rows(FIXTURES / "observations.csv"))
    report = build_cross_platform_report(ingested, owner_context=OWNER_BASELINE_SNAPSHOT)
    write_json(out / "cross_platform_report.json", report)
    (out / "cross_platform_report.md").write_text(report_markdown(report), encoding="utf-8")

    article = read_json(FIXTURES / "approved_article.json")
    extras = read_json(FIXTURES / "storyboard_and_rewrites.json")
    packages = build_platform_packages(article, storyboard=extras["storyboard"], candidate_rewrites=extras["candidate_rewrites"])
    write_json(out / "platform_packages.json", packages)
    (out / "platform_packages.md").write_text(packages_markdown(packages), encoding="utf-8")

    visual_summary = None
    if not args.skip_video:
        from src.crossplatform.visual_qa import run_visual_qa

        with tempfile.TemporaryDirectory(prefix="xp_preview_") as tmp:
            work = Path(tmp)
            video, overlays = render_sample_video(work)
            good = run_visual_qa(video=video, output_dir=work / "good", overlay_texts=overlays)
            defect_video = make_defect_video(video, work)
            bad = run_visual_qa(video=defect_video, output_dir=work / "defect", overlay_texts=overlays + [OVERLONG_OVERLAY])
            for report_obj, name, sheet_dir, sheet_name in (
                (good, "visual_qa_report.json", work / "good", "contact_sheet.jpg"),
                (bad, "visual_qa_defect_report.json", work / "defect", "contact_sheet_defect.jpg"),
            ):
                report_obj["input"]["video"] = f"<temporary {Path(report_obj['input']['video']).name}>"
                report_obj["contact_sheet"] = sheet_name
                report_obj["data_classification"] = "synthetic_render_not_a_published_video"
                write_json(out / name, report_obj)
                (out / sheet_name).write_bytes((sheet_dir / "contact_sheet.jpg").read_bytes())
            visual_summary = {
                "sample_status": good["status"],
                "sample_issues": [i["code"] for i in good["issues"]],
                "defect_status": bad["status"],
                "defect_issues": [i["code"] for i in bad["issues"]],
            }

    index = {
        "schema": 1,
        "feature_flag": "CROSS_PLATFORM_GROWTH_ENABLED=0 (default)",
        "data_classification": {
            "analytics": report["dataset_labels"],
            "article": packages["source"]["data_classification"],
            "visual": "synthetic_render_not_a_published_video",
        },
        "analytics_quality": report["dataset_quality"],
        "packaging_status": {p: pkg["status"] for p, pkg in packages["packages"].items()},
        "visual_qa": visual_summary,
        "safety": {
            "publishing_invoked": False,
            "scheduling_effect": "none",
            "production_weights_changed": False,
            "production_narration_changed": False,
            "paid_model_calls": 0,
            "network_calls": 0,
        },
    }
    write_json(out / "index.json", index)
    print(json.dumps(index, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
