"""Offline visual quality gate for rendered Shorts/Reels/TikTok videos.

Uses only local tools already required by the renderer: ffprobe/ffmpeg and
Pillow. The gate samples many frames (dense in the opening, spread across the
rest), runs ffmpeg ``blackdetect`` over the whole video, and reports warnings
with timestamps and numeric evidence.

Design rules:
- never pass a video on the evidence of one frame (``min_frames``);
- a dark frame with real detail is not a black frame;
- the renderer's 0.18 s fade-in is expected and is not an error by itself;
- the result is a report and a contact sheet only; nothing is replaced,
  re-rendered or published (``approved_for_publication`` is always False).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageStat


LAYOUT_PROFILES: dict[str, dict[str, Any]] = {
    # Mirrors src/render/short_v2.py: 1080x1920, headline block x=64..1016
    # starting around y=966..1110 and running into the narration panel.
    "short_v2": {
        "width": 1080,
        "height": 1920,
        "title_region": (64, 900, 1016, 1500),
        "overflow_band": (900, 1500),
        "side_margin_px": 32,
        "title_font_size": 72,
        "title_font_size_long": 61,
        "title_max_width": 1080 - 128,
        "title_max_lines": 4,
        "body_font_size": 34,
        "body_max_lines": 4,
    },
}
ANALYSIS_WIDTH = 270
MIN_FRAMES = 6
OPENING_TIMESTAMPS = (0.0, 0.25, 0.5, 1.0, 1.5, 2.0)
SPREAD_FRAMES = 8
EXPECTED_FADE_SECONDS = 0.25
BLACK_OPENING_SECONDS = 0.4

# Thresholds on a 0..255 luma scale, at analysis resolution.
NEAR_BLACK_MEAN = 22.0
NEAR_BLACK_P98 = 45.0
DETAIL_EDGE_DENSITY = 0.02
DETAIL_ENTROPY = 3.0
BLANK_STD = 5.0
STATIC_DIFF = 1.5


class VisualQAError(RuntimeError):
    pass


# ---------------------------------------------------------------- probing

def probe_video(path: Path) -> dict[str, Any]:
    if not shutil.which("ffprobe"):
        raise VisualQAError("ffprobe is not installed")
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,codec_name,width,height,nb_frames,avg_frame_rate:stream_side_data=rotation:format=duration,size",
         "-of", "json", str(path)],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        return {"ok": False, "error": (result.stderr or "ffprobe failed").strip()[:400]}
    data = json.loads(result.stdout or "{}")
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    fmt = data.get("format", {})
    try:
        duration = float(fmt.get("duration") or 0)
    except ValueError:
        duration = 0.0
    rotation = 0
    for side in (video or {}).get("side_data_list", []) or []:
        if "rotation" in side:
            rotation = int(side["rotation"])
    width, height = (video or {}).get("width"), (video or {}).get("height")
    if rotation in (90, -90, 270, -270) and width and height:
        width, height = height, width
    return {
        "ok": video is not None,
        "error": None if video else "no video stream",
        "codec": (video or {}).get("codec_name"),
        "width": width,
        "height": height,
        "duration": duration,
        "has_audio": audio is not None,
        "size_bytes": int(fmt.get("size") or 0),
    }


def black_intervals(path: Path, *, min_duration: float = 0.1, pix_th: float = 0.10) -> list[dict[str, float]]:
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vf",
         f"blackdetect=d={min_duration}:pix_th={pix_th}", "-an", "-f", "null", "-"],
        capture_output=True, text=True, timeout=300,
    )
    intervals = []
    for match in re.finditer(r"black_start:([\d.]+)\s+black_end:([\d.]+)\s+black_duration:([\d.]+)", result.stderr):
        start, end, duration = (float(v) for v in match.groups())
        intervals.append({"start": round(start, 3), "end": round(end, 3), "duration": round(duration, 3)})
    return intervals


def sample_timestamps(duration: float) -> list[float]:
    stamps = [t for t in OPENING_TIMESTAMPS if t < max(duration - 0.05, 0.01)]
    start = 2.5
    end = max(duration - 0.15, 0.0)
    if end > start:
        step = (end - start) / max(SPREAD_FRAMES - 1, 1)
        stamps += [round(start + i * step, 3) for i in range(SPREAD_FRAMES)]
    return sorted(set(round(t, 3) for t in stamps))


def extract_frame(path: Path, timestamp: float, output: Path, width: int = ANALYSIS_WIDTH) -> bool:
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", f"{timestamp:.3f}", "-i", str(path),
         "-frames:v", "1", "-vf", f"scale={width}:-2", str(output)],
        capture_output=True, text=True, timeout=60,
    )
    return result.returncode == 0 and output.exists() and output.stat().st_size > 0


# ---------------------------------------------------------------- frame analysis

def _percentile(histogram: list[int], fraction: float) -> float:
    total = sum(histogram)
    if not total:
        return 0.0
    threshold = total * fraction
    running = 0
    for value, count in enumerate(histogram):
        running += count
        if running >= threshold:
            return float(value)
    return 255.0


def frame_stats(image: Image.Image) -> dict[str, float]:
    gray = image.convert("L")
    stat = ImageStat.Stat(gray)
    histogram = gray.histogram()
    edges = gray.filter(ImageFilter.FIND_EDGES)
    # FIND_EDGES produces artefacts on the 1px border; ignore it.
    if gray.width > 4 and gray.height > 4:
        edges = edges.crop((1, 1, gray.width - 1, gray.height - 1))
    edge_hist = edges.histogram()
    pixels = edges.width * edges.height
    edge_density = sum(edge_hist[40:]) / pixels if pixels else 0.0
    return {
        "mean_luma": round(stat.mean[0], 2),
        "std_luma": round(stat.stddev[0], 2),
        "p98_luma": _percentile(histogram, 0.98),
        "entropy": round(gray.entropy(), 3),
        "edge_density": round(edge_density, 4),
    }


def classify_frame(stats: dict[str, float]) -> str:
    detailed = stats["edge_density"] >= DETAIL_EDGE_DENSITY or stats["entropy"] >= DETAIL_ENTROPY
    if stats["mean_luma"] <= NEAR_BLACK_MEAN and stats["p98_luma"] <= NEAR_BLACK_P98 and not detailed:
        return "near_black"
    if stats["std_luma"] <= BLANK_STD and stats["edge_density"] < 0.005:
        return "blank_uniform"
    if stats["mean_luma"] <= 45 and detailed:
        return "dark_detailed"
    return "ok"


def _scaled_box(box: tuple[int, int, int, int], profile: dict[str, Any], image: Image.Image) -> tuple[int, int, int, int]:
    sx = image.width / profile["width"]
    sy = image.height / profile["height"]
    return (int(box[0] * sx), int(box[1] * sy), int(box[2] * sx), int(box[3] * sy))


def title_region_check(image: Image.Image, profile: dict[str, Any]) -> dict[str, Any]:
    region = image.convert("L").crop(_scaled_box(profile["title_region"], profile, image))
    histogram = region.histogram()
    pixels = max(1, region.width * region.height)
    bright = sum(histogram[200:]) / pixels
    dark = sum(histogram[:90]) / pixels
    mean = ImageStat.Stat(region).mean[0]
    present = bright >= 0.008
    readable = present and dark >= 0.30
    return {
        "bright_text_fraction": round(bright, 4),
        "dark_background_fraction": round(dark, 4),
        "region_mean_luma": round(mean, 2),
        "title_present": present,
        "title_readable": readable,
    }


def margin_overflow_check(image: Image.Image, profile: dict[str, Any]) -> dict[str, Any]:
    gray = image.convert("L")
    sx = image.width / profile["width"]
    sy = image.height / profile["height"]
    top, bottom = int(profile["overflow_band"][0] * sy), int(profile["overflow_band"][1] * sy)
    margin = max(1, int(profile["side_margin_px"] * sx))
    fractions = {}
    for side, box in (("left", (0, top, margin, bottom)), ("right", (image.width - margin, top, image.width, bottom))):
        strip = gray.crop(box)
        hist = strip.histogram()
        fractions[side] = round(sum(hist[200:]) / max(1, strip.width * strip.height), 4)
    return {"bright_fraction_in_margins": fractions, "overflow_suspected": any(v >= 0.04 for v in fractions.values())}


def check_text_layout(text: str, *, profile_name: str = "short_v2", role: str = "title") -> dict[str, Any]:
    """Deterministic pre-render check with the renderer's own font and wrapping.

    ``short_v2._wrap`` silently truncates with an ellipsis when text needs more
    lines than allowed; that is reported here as overflow.
    """
    from ..render.short_v2 import _font, _wrap  # local import: renderer is optional for analytics

    profile = LAYOUT_PROFILES[profile_name]
    if role == "title":
        size = profile["title_font_size"] if len(text) < 52 else profile["title_font_size_long"]
        font = _font(size, True)
        rendered = text.upper()
        max_lines = profile["title_max_lines"]
    else:
        size = profile["body_font_size"]
        font = _font(size, False)
        rendered = text
        max_lines = profile["body_max_lines"]
    max_width = profile["title_max_width"]
    canvas = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    lines = _wrap(canvas, rendered, font, max_width, max_lines)
    widths = [canvas.textbbox((0, 0), line, font=font)[2] for line in lines]
    truncated = bool(lines) and lines[-1].endswith("…") and not rendered.rstrip().endswith("…")
    too_wide = [i for i, w in enumerate(widths) if w > max_width]
    return {
        "role": role,
        "text": text,
        "font_size": size,
        "max_width_px": max_width,
        "max_lines": max_lines,
        "lines": lines,
        "line_widths_px": widths,
        "truncated_by_renderer": truncated,
        "lines_exceeding_width": too_wide,
        "overflow": truncated or bool(too_wide),
    }


# ---------------------------------------------------------------- gate

def _issue(code: str, severity: str, detail: str, **evidence: Any) -> dict[str, Any]:
    return {"code": code, "severity": severity, "detail": detail, "evidence": evidence}


def _analyze_frames(frames: list[tuple[float, Path]], profile: dict[str, Any], *, title_expected_until: float | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    analyzed: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    previous: Image.Image | None = None
    diffs: list[float] = []
    for timestamp, path in frames:
        with Image.open(path) as raw:
            image = raw.convert("RGB")
        stats = frame_stats(image)
        label = classify_frame(stats)
        entry: dict[str, Any] = {"t": timestamp, "file": path.name, "classification": label, "stats": stats}
        if title_expected_until is not None and 0.4 <= timestamp <= title_expected_until and label in {"ok", "dark_detailed"}:
            entry["title_region"] = title_region_check(image, profile)
            entry["margins"] = margin_overflow_check(image, profile)
        if previous is not None and previous.size == image.size:
            diff = ImageStat.Stat(ImageChops.difference(previous.convert("L"), image.convert("L"))).mean[0]
            entry["diff_from_previous"] = round(diff, 2)
            diffs.append(diff)
        previous = image
        analyzed.append(entry)

    for entry in analyzed:
        if entry["classification"] == "blank_uniform":
            issues.append(_issue("blank_frame", "warning", "Uniform frame with no visible detail.", t=entry["t"], stats=entry["stats"]))
        title = entry.get("title_region")
        if title and not title["title_present"]:
            issues.append(_issue("title_region_missing", "warning", "Expected headline area has no text-like bright pixels.", t=entry["t"], **title))
        elif title and not title["title_readable"]:
            issues.append(_issue("title_region_low_contrast", "warning", "Headline pixels present but background is not dark enough for white text.", t=entry["t"], **title))
        margins = entry.get("margins")
        if margins and margins["overflow_suspected"]:
            issues.append(_issue("text_overflow_suspected", "warning", "Bright pixels reach the side margins of the headline band.", t=entry["t"], **margins))
    if len(diffs) >= 3 and max(diffs) < STATIC_DIFF:
        issues.append(_issue("very_low_visual_variation", "warning", "All sampled frames are nearly identical.",
                             max_mean_abs_diff=round(max(diffs), 3), samples=len(analyzed)))
    return analyzed, issues


def contact_sheet(frames: list[tuple[float, Path]], analyzed: list[dict[str, Any]], issues: list[dict[str, Any]], output: Path, *, columns: int = 5, thumb_width: int = 162) -> Path:
    flagged_t = {}
    for issue in issues:
        t = issue["evidence"].get("t")
        if t is not None:
            flagged_t.setdefault(t, issue["severity"])
    thumbs = []
    for (timestamp, path), entry in zip(frames, analyzed):
        with Image.open(path) as raw:
            image = raw.convert("RGB")
        height = int(image.height * thumb_width / image.width)
        thumbs.append((timestamp, image.resize((thumb_width, height)), entry))
    if not thumbs:
        raise VisualQAError("no frames for contact sheet")
    label_h = 30
    cell_h = thumbs[0][1].height + label_h
    rows = (len(thumbs) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * (thumb_width + 6) + 6, rows * (cell_h + 6) + 6), (24, 26, 30))
    draw = ImageDraw.Draw(sheet)
    for index, (timestamp, thumb, entry) in enumerate(thumbs):
        x = 6 + (index % columns) * (thumb_width + 6)
        y = 6 + (index // columns) * (cell_h + 6)
        sheet.paste(thumb, (x, y))
        severity = flagged_t.get(timestamp)
        colour = {"error": (220, 50, 50), "warning": (240, 160, 0)}.get(severity or "", (60, 170, 90))
        if entry["classification"] == "near_black" and not severity:
            colour = (120, 120, 120)
        draw.rectangle((x, y + thumb.height, x + thumb_width, y + cell_h), fill=colour)
        draw.text((x + 4, y + thumb.height + 3), f"t={timestamp:.2f}s", fill=(255, 255, 255))
        draw.text((x + 4, y + thumb.height + 15), entry["classification"][:24], fill=(255, 255, 255))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, "JPEG", quality=78, optimize=True)
    return output


def _frames_from_dir(frames_dir: Path) -> list[tuple[float, Path]]:
    files = sorted(p for p in frames_dir.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"})
    result = []
    for index, path in enumerate(files):
        match = re.search(r"t[=_-]?(\d+(?:\.\d+)?)", path.stem)
        result.append((float(match.group(1)) if match else float(index), path))
    return sorted(result)


def run_visual_qa(
    *,
    video: Path | None = None,
    frames_dir: Path | None = None,
    output_dir: Path,
    profile_name: str = "short_v2",
    title_expected_until: float | None = 2.0,
    overlay_texts: list[str] | None = None,
    min_frames: int = MIN_FRAMES,
) -> dict[str, Any]:
    if (video is None) == (frames_dir is None):
        raise VisualQAError("pass exactly one of video or frames_dir")
    profile = LAYOUT_PROFILES[profile_name]
    output_dir.mkdir(parents=True, exist_ok=True)
    issues: list[dict[str, Any]] = []
    info: list[dict[str, Any]] = []
    probe: dict[str, Any] = {}
    intervals: list[dict[str, float]] = []
    work = Path(tempfile.mkdtemp(prefix="visual_qa_"))
    try:
        if video is not None:
            video = Path(video)
            if not video.exists() or video.stat().st_size == 0:
                issues.append(_issue("empty_or_missing_file", "error", "Video file is missing or empty.", path=str(video)))
                frames: list[tuple[float, Path]] = []
            else:
                probe = probe_video(video)
                if not probe["ok"] or not probe.get("duration"):
                    issues.append(_issue("corrupt_or_unreadable_video", "error", "ffprobe could not read a video stream with duration.", probe=probe))
                    frames = []
                else:
                    frames = []
                    failed = []
                    for t in sample_timestamps(probe["duration"]):
                        target = work / f"frame_t{t:07.3f}.png"
                        (frames.append((t, target)) if extract_frame(video, t, target) else failed.append(t))
                    if failed:
                        issues.append(_issue("frame_decode_failed", "error", "Some sampled timestamps could not be decoded.", timestamps=failed))
                    intervals = black_intervals(video)
        else:
            frames = _frames_from_dir(Path(frames_dir))
            if frames:
                with Image.open(frames[0][1]) as first:
                    width, height = first.size
                probe = {"ok": True, "width": width, "height": height, "duration": None, "source": "frames_dir"}
                sizes = set()
                for _, path in frames:
                    try:
                        with Image.open(path) as image:
                            image.verify()
                        with Image.open(path) as image:
                            sizes.add(image.size)
                    except Exception as exc:  # corrupt image file
                        issues.append(_issue("corrupt_frame_file", "error", "Frame image cannot be decoded.", file=path.name, error=str(exc)[:200]))
                if len(sizes) > 1:
                    issues.append(_issue("inconsistent_frame_sizes", "error", "Frames have different dimensions.", sizes=sorted(sizes)))
                frames = [(t, p) for t, p in frames if not any(i["evidence"].get("file") == p.name for i in issues)]

        # Resolution / aspect ratio.
        width, height = probe.get("width"), probe.get("height")
        if width and height:
            ratio = width / height
            if abs(ratio - 9 / 16) > 0.01:
                issues.append(_issue("invalid_aspect_ratio", "error", "Expected vertical 9:16.", width=width, height=height, ratio=round(ratio, 4)))
            elif width < 720:
                issues.append(_issue("resolution_too_low", "error", "Below 720x1280.", width=width, height=height))
            elif width < profile["width"]:
                issues.append(_issue("below_target_resolution", "warning", f"Target is {profile['width']}x{profile['height']}.", width=width, height=height))

        # Frame analysis (frames from video are analysed at reduced width,
        # frames from a directory at their own size).
        analysis_frames = []
        for t, path in frames:
            with Image.open(path) as raw:
                image = raw.convert("RGB")
            if image.width > ANALYSIS_WIDTH * 2:
                small = work / f"a_{path.stem}.png"
                image.resize((ANALYSIS_WIDTH, int(image.height * ANALYSIS_WIDTH / image.width))).save(small)
                analysis_frames.append((t, small))
            else:
                analysis_frames.append((t, path))
        analyzed, frame_issues = _analyze_frames(analysis_frames, profile, title_expected_until=title_expected_until)
        issues.extend(frame_issues)

        # Opening: combine sampled frames with blackdetect intervals.
        opening = [a for a in analyzed if a["t"] <= 1.0]
        black_opening = [a["t"] for a in opening if a["classification"] in {"near_black", "blank_uniform"}]
        opening_interval = next((i for i in intervals if i["start"] <= 0.05), None)
        dark_detailed_opening = [a["t"] for a in opening if a["classification"] == "dark_detailed"]
        if opening_interval and opening_interval["duration"] >= BLACK_OPENING_SECONDS:
            issues.append(_issue("black_opening", "error", "Video opens on a black/blank screen.", interval=opening_interval, sampled_blank_timestamps=black_opening))
        elif opening and len(black_opening) >= 3 and len(black_opening) == len(opening):
            issues.append(_issue("black_opening", "error", "All opening samples are black/blank.", sampled_blank_timestamps=black_opening))
        elif black_opening and set(black_opening) <= {0.0} and (not opening_interval or opening_interval["duration"] <= EXPECTED_FADE_SECONDS):
            info.append({"code": "fade_in_first_frame", "detail": "First frame is black; consistent with the renderer's 0.18 s fade-in. Use a non-black thumbnail.", "t": 0.0})
        elif black_opening:
            issues.append(_issue("blank_opening_frames", "warning", "Some opening samples are black/blank.", sampled_blank_timestamps=black_opening))
        if dark_detailed_opening:
            info.append({"code": "dark_but_detailed_opening", "detail": "Dark opening frames contain detail; not treated as black.", "timestamps": dark_detailed_opening})

        for interval in intervals:
            if interval["start"] > 0.05 and interval["duration"] >= 0.5:
                issues.append(_issue("black_segment", "warning", "Black interval inside the video.", interval=interval))

        # Single-frame evidence is never enough.
        usable = [a for a in analyzed if a["classification"] != "near_black"]
        if len(analyzed) < min_frames:
            issues.append(_issue("insufficient_frame_evidence", "error", f"Only {len(analyzed)} frames analysed; at least {min_frames} required.", analysed=len(analyzed)))
        elif len(usable) < max(2, min_frames // 2):
            issues.append(_issue("mostly_black_samples", "error", "Too few non-black samples to judge the video.", usable=len(usable), analysed=len(analyzed)))

        layout_checks = [check_text_layout(text, profile_name=profile_name) for text in (overlay_texts or [])]
        for check in layout_checks:
            if check["overflow"]:
                issues.append(_issue("title_text_overflow", "warning", "Overlay text does not fit the renderer's title box and would be truncated.", text=check["text"], lines=check["lines"]))

        sheet_path = None
        if frames:
            sheet_path = contact_sheet(analysis_frames, analyzed, issues, output_dir / "contact_sheet.jpg")
    finally:
        shutil.rmtree(work, ignore_errors=True)

    errors = [i for i in issues if i["severity"] == "error"]
    warnings = [i for i in issues if i["severity"] == "warning"]
    status = "fail" if errors else "warn" if warnings else "pass"
    return {
        "schema": 1,
        "module": "cross_platform_visual_qa",
        "input": {"video": str(video) if video else None, "frames_dir": str(frames_dir) if frames_dir else None, "profile": profile_name},
        "probe": probe,
        "black_intervals": intervals,
        "frames_analysed": len(analyzed),
        "frames": analyzed,
        "layout_checks": layout_checks,
        "issues": issues,
        "info": info,
        "status": status,
        "approved_for_publication": False,
        "replacement_or_publication_performed": False,
        "contact_sheet": sheet_path.name if sheet_path else None,
    }
