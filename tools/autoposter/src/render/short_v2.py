from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

from ..ai.storyboard import Scene, Storyboard


WIDTH = 1080
HEIGHT = 1920
FPS = 30
ORANGE = (255, 107, 0)
WHITE = (246, 247, 249)
MUTED = (180, 187, 196)
DARK = (15, 18, 22)


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", errors="replace")
        raise RuntimeError(f"ffmpeg failed: {err[-5000:]}")


def media_duration(path: Path) -> float:
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        return float((proc.stdout or b"0").decode().strip())
    except Exception:
        return 0.0


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def _cover(image: Image.Image, width: int, height: int) -> Image.Image:
    image = image.convert("RGB")
    iw, ih = image.size
    scale = max(width / max(iw, 1), height / max(ih, 1))
    nw, nh = int(iw * scale), int(ih * scale)
    resized = image.resize((nw, nh), Image.LANCZOS)
    left = max(0, (nw - width) // 2)
    top = max(0, (nh - height) // 2)
    return resized.crop((left, top, left + width, top + height))


def _showcase(image: Image.Image, width: int, height: int, top: int = 230) -> Image.Image:
    """Whole landscape product photo on a blurred copy of itself.

    Cover-cropping a side shot of a trailer to 9:16 leaves only a patch of the
    body; partner episodes must show the whole machine."""
    image = image.convert("RGB")
    if image.width <= image.height:
        return _cover(image, width, height)
    back = _cover(image, width, height).filter(ImageFilter.GaussianBlur(radius=28))
    back = Image.blend(back, Image.new("RGB", (width, height), DARK), 0.45)
    fg_h = round(image.height * width / image.width)
    back.paste(image.resize((width, fg_h), Image.LANCZOS), (0, top))
    return back


_KEEP_TOGETHER = re.compile(r"(?<=\d) (?=\d{3}\b)|(?<=\d) (?=(?:₽|%|т|м|ч|км|кг|руб)\b)|(?<=\d) (?=[₽%])", re.I)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int, max_lines: int) -> list[str]:
    # Never break "300 000 ₽" or "5 т" across lines.
    glued = _KEEP_TOGETHER.sub("\u00a0", str(text or ""))
    words = [w.replace("\u00a0", " ") for w in re.split(r"[ \t\r\n]+", glued.strip()) if w]
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if not current or draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
            if len(lines) >= max_lines - 1:
                break
    if current and len(lines) < max_lines:
        lines.append(current)

    consumed = " ".join(lines)
    original = " ".join(words)
    if lines and consumed != original:
        last = lines[-1].rstrip(" .,:;!-")
        while last and draw.textbbox((0, 0), last + "…", font=font)[2] > max_width:
            last = last.rsplit(" ", 1)[0] if " " in last else last[:-1]
        lines[-1] = (last or lines[-1][:8]) + "…"
    return lines


def _gradient_overlay(width: int, height: int) -> Image.Image:
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(height):
        top = max(0.0, 1.0 - y / 620.0)
        bottom = max(0.0, (y - 980.0) / max(1.0, height - 980.0))
        alpha = int(min(235, 65 + top * 100 + bottom * 175))
        draw.line((0, y, width, y), fill=(7, 9, 12, alpha))
    return overlay


SITE_DOMAIN = "spec-avtoportal.ru"


def _draw_cta(draw: ImageDraw.ImageDraw, *, partner_domain: str = "", explainer: bool = False, lead: list[str] | None = None) -> None:
    """Big ending card: where to read the full story and a subscribe nudge.

    Partner episodes (SAT) point to the partner site instead of ours."""
    panel = (48, 560, WIDTH - 48, 1340)
    draw.rounded_rectangle(panel, radius=36, fill=(10, 13, 17, 228), outline=ORANGE + (255,), width=4)
    cx = WIDTH // 2

    def centered(text: str, y: int, font: ImageFont.ImageFont, fill: tuple) -> int:
        w = draw.textbbox((0, 0), text, font=font)[2]
        draw.text((cx - w // 2, y), text, font=font, fill=fill)
        return y + int(getattr(font, "size", 40) * 1.25)

    y = 640
    domain = partner_domain or SITE_DOMAIN
    if lead and len(lead) >= 2:
        lead = (str(lead[0]), str(lead[1]))
    elif partner_domain:
        lead = ("ЦЕНЫ И КОМПЛЕКТАЦИИ", "— У ПРОИЗВОДИТЕЛЯ")
    elif explainer:
        lead = ("ПОЛНЫЙ РАЗБОР", "— НА САЙТЕ")
    else:
        lead = ("ПОЛНАЯ НОВОСТЬ", "И РАЗБОР — НА САЙТЕ")
    y = centered(lead[0], y, _font(46, True), MUTED + (255,))
    y = centered(lead[1], y, _font(46, True), MUTED + (255,))
    y += 40
    domain_font = _font(86, True)
    while draw.textbbox((0, 0), domain, font=domain_font)[2] > WIDTH - 160 and domain_font.size > 50:
        domain_font = _font(domain_font.size - 4, True)
    y = centered(domain, y, domain_font, ORANGE + (255,))
    y += 30
    y = centered("ссылка — в описании", y, _font(40, False), WHITE + (255,))
    draw.line((cx - 180, y + 30, cx + 180, y + 30), fill=(60, 66, 74, 255), width=3)
    y += 80
    button = (cx - 330, y, cx + 330, y + 110)
    draw.rounded_rectangle(button, radius=55, fill=ORANGE + (255,))
    sub_font = _font(46, True)
    label = "ПОДПИСЫВАЙТЕСЬ"
    w = draw.textbbox((0, 0), label, font=sub_font)[2]
    draw.text((cx - w // 2, y + 28), label, font=sub_font, fill=(255, 255, 255, 255))
    y += 150
    centered("новости грузовой техники каждый день", y, _font(34, False), MUTED + (255,))


def render_scene_frame(
    scene: Scene,
    visual_path: Path,
    output: Path,
    *,
    index: int,
    total: int,
    format_name: str,
    platform: str = "standard",
) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with Image.open(visual_path) as source:
            fit = _showcase if format_name.lower() == "partner" else _cover
            base = fit(source, WIDTH, HEIGHT)
    except Exception:
        base = Image.new("RGB", (WIDTH, HEIGHT), DARK)

    # Editorial cinematic treatment.
    base = base.filter(ImageFilter.GaussianBlur(radius=0.3))
    image = Image.alpha_composite(base.convert("RGBA"), _gradient_overlay(WIDTH, HEIGHT))
    draw = ImageDraw.Draw(image, "RGBA")

    brand_font = _font(32, True)
    label_font = _font(25, True)
    title_font = _font(72 if len(scene.overlay) < 52 else 61, True)
    small_font = _font(26, False)

    # Identity is kept for Instagram/YouTube. TikTok API guidelines prohibit
    # superimposed promotional branding/watermarks, so the TikTok export is clean.
    is_tiktok = platform.lower() == "tiktok"
    if not is_tiktok:
        draw.rounded_rectangle((54, 52, 118, 116), radius=14, fill=ORANGE + (255,))
        draw.text((71, 72), "САП", font=_font(18, True), fill=(255, 255, 255, 255))
        draw.text((140, 64), "СпецАвтоПортал", font=brand_font, fill=WHITE + (255,))
        counter = f"{index:02d}/{total:02d}"
        counter_w = draw.textbbox((0, 0), counter, font=label_font)[2]
        draw.text((WIDTH - 56 - counter_w, 72), counter, font=label_font, fill=MUTED + (255,))

    # Format / section marker.
    format_label = {"breaking": "НОВОСТЬ", "news": "НОВОСТЬ", "partner": "ПАРТНЁР · РЕКЛАМА"}.get(format_name.lower(), "РАЗБОР")
    badge_w = draw.textbbox((0, 0), format_label, font=label_font)[2] + 44
    badge_y = 132 if not is_tiktok else 72
    draw.rounded_rectangle((56, badge_y, 56 + badge_w, badge_y + 50), radius=22, fill=(15, 18, 22, 200), outline=ORANGE + (220,), width=2)
    draw.text((78, badge_y + 11), format_label, font=label_font, fill=ORANGE + (255,))

    # Final scene on YouTube/Instagram: a large call to action with the site
    # address — the small footer line alone brought almost no visits.
    if not is_tiktok and index == total:
        _draw_cta(
            draw,
            partner_domain=scene.overlay if scene.id == "cta-partner" else "",
            explainer=format_name.lower() == "explainer",
            lead=list(getattr(scene, "cta_lead", []) or []),
        )
        image.convert("RGB").save(output, "PNG", optimize=True)
        return output

    # Headline block. Safe zone leaves room for native social UI at bottom.
    x = 64
    max_w = WIDTH - 128
    lines = _wrap(draw, scene.overlay.upper(), title_font, max_w, 4)
    y = 1110 - max(0, len(lines) - 2) * 72
    draw.rectangle((x, y - 26, x + 130, y - 17), fill=ORANGE + (255,))
    for line in lines:
        draw.text((x, y), line, font=title_font, fill=WHITE + (255,), stroke_width=2, stroke_fill=(0, 0, 0, 160))
        y += int(getattr(title_font, "size", 64) * 1.12)

    # Supporting copy is part of the editorial frame, not karaoke subtitles.
    body_font = _font(34, False)
    body_lines = _wrap(draw, scene.narration, body_font, max_w, 4)
    body_y = min(max(y + 34, 1370), 1550)
    if body_lines:
        panel_h = len(body_lines) * 48 + 44
        draw.rounded_rectangle(
            (48, body_y - 18, WIDTH - 48, body_y + panel_h),
            radius=24,
            fill=(10, 13, 17, 176),
        )
        by = body_y
        for line in body_lines:
            draw.text((64, by), line, font=body_font, fill=(224, 228, 233, 255))
            by += 48

    if not is_tiktok:
        draw.text((64, 1735), "spec-avtoportal.ru", font=small_font, fill=MUTED + (255,))
        draw.text((64, 1780), "рынок · техника · регламенты", font=small_font, fill=(128, 136, 146, 255))

    image.convert("RGB").save(output, "PNG", optimize=True)
    return output


def _scaled_durations(
    storyboard: Storyboard,
    audio_seconds: float,
    scene_audio_seconds: list[float] | None = None,
) -> list[float]:
    if scene_audio_seconds and len(scene_audio_seconds) == len(storyboard.scenes):
        # Legacy scene audio is already padded to >=2.8s. Continuous narration
        # supplies real word-boundary timings and must not be shifted by an
        # additional visual minimum, otherwise the next frame starts late.
        durations = [max(0.30, float(value)) for value in scene_audio_seconds]
        # Compensate only for tiny codec/container rounding drift on the final scene.
        drift = max(0.0, audio_seconds - sum(durations))
        if durations and drift > 0:
            durations[-1] += drift + 0.08
        return durations

    base = [max(3.0, float(scene.seconds)) for scene in storyboard.scenes]
    planned = sum(base)
    target = max(planned, audio_seconds + 0.45)
    factor = target / max(planned, 1.0)
    return [x * factor for x in base]


def render_short(
    storyboard: Storyboard,
    visual_paths: list[Path],
    audio_path: Path,
    output: Path,
    work_dir: Path,
    *,
    platform: str = "standard",
    scene_audio_seconds: list[float] | None = None,
) -> dict[str, object]:
    if len(storyboard.scenes) != len(visual_paths):
        raise ValueError("scene/visual count mismatch")

    work_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = work_dir / "frames"
    segments_dir = work_dir / "segments"
    frames_dir.mkdir(parents=True, exist_ok=True)
    segments_dir.mkdir(parents=True, exist_ok=True)

    audio_seconds = media_duration(audio_path)
    durations = _scaled_durations(storyboard, audio_seconds, scene_audio_seconds)
    segments: list[Path] = []

    for index, (scene, visual, duration) in enumerate(zip(storyboard.scenes, visual_paths, durations), 1):
        frame = frames_dir / f"scene_{index:02d}.png"
        segment = segments_dir / f"scene_{index:02d}.mp4"
        render_scene_frame(
            scene,
            visual,
            frame,
            index=index,
            total=len(storyboard.scenes),
            format_name=storyboard.format,
            platform=platform,
        )
        fade_out = max(0.05, duration - 0.20)
        vf = (
            "zoompan="
            "z='min(max(zoom,pzoom)+0.00055,1.055)':"
            "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d=1:s={WIDTH}x{HEIGHT}:fps={FPS},"
            f"fade=t=in:st=0:d=0.18,fade=t=out:st={fade_out:.3f}:d=0.18,"
            "format=yuv420p"
        )
        _run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-loop", "1", "-i", str(frame),
            "-t", f"{duration:.3f}",
            "-vf", vf,
            "-r", str(FPS),
            "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-pix_fmt", "yuv420p",
            str(segment),
        ])
        segments.append(segment)

    concat_file = work_dir / "concat.txt"
    concat_file.write_text(
        "".join(f"file '{segment.resolve()}'\n" for segment in segments),
        encoding="utf-8",
    )
    silent = work_dir / "silent.mp4"
    _run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c", "copy", str(silent),
    ])

    output.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(silent),
        "-i", str(audio_path),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "160k",
        "-shortest",
        str(output),
    ])

    first_frame = frames_dir / "scene_01.png"
    return {
        "video": str(output),
        "thumbnail": str(first_frame),
        "audio_seconds": audio_seconds,
        "video_seconds": media_duration(output),
        "durations": durations,
    }
