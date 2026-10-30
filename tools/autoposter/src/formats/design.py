"""Shared deterministic SpecAvtoPortal image rendering and visual QA."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps


INK = (20, 24, 30)
PAPER = (245, 246, 242)
ORANGE = (244, 119, 33)
MUTED = (94, 101, 111)
WHITE = (255, 255, 255)
FONT_CANDIDATES = {
    "regular": (
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ),
    "bold": (
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    ),
}


def approved_local_images(entries: list[dict[str, Any]] | None) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    approved: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    for index, row in enumerate(entries or [], 1):
        path = Path(str(row.get("path") or ""))
        if row.get("rights_confirmed") is not True:
            warnings.append({"code": "image_rights_not_confirmed", "item": str(index)})
            continue
        if not path.is_file() or path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            warnings.append({"code": "approved_image_unavailable", "item": str(index)})
            continue
        approved.append({"path": str(path), "credit": str(row.get("credit") or ""), "source_url": str(row.get("source_url") or "")})
    return approved, warnings


def editorial_background(size: tuple[int, int], approved_image: str | None, *, dark: bool) -> Image.Image:
    base_color = INK if dark else PAPER
    if not approved_image:
        return Image.new("RGB", size, base_color)
    source = Image.open(approved_image).convert("RGB")
    fitted = ImageOps.fit(source, size, method=Image.Resampling.LANCZOS)
    overlay_color = (12, 16, 22, 190) if dark else (245, 246, 242, 215)
    layer = Image.new("RGBA", size, overlay_color)
    return Image.alpha_composite(fitted.convert("RGBA"), layer).convert("RGB")


def font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    for candidate in FONT_CANDIDATES["bold" if bold else "regular"]:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def wrap(draw: ImageDraw.ImageDraw, text: str, selected_font: ImageFont.ImageFont, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in str(text).splitlines() or [""]:
        words = paragraph.split()
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if not current or draw.textbbox((0, 0), candidate, font=selected_font)[2] <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
    return lines


def draw_text_block(
    draw: ImageDraw.ImageDraw,
    text: str,
    box: tuple[int, int, int, int],
    *,
    max_size: int,
    min_size: int,
    bold: bool,
    fill: tuple[int, int, int],
    spacing: float = 1.18,
) -> dict[str, Any]:
    left, top, right, bottom = box
    selected = font(max_size, bold=bold)
    lines = wrap(draw, text, selected, right - left)
    while getattr(selected, "size", min_size) > min_size:
        line_height = int(getattr(selected, "size", min_size) * spacing)
        widest = max((draw.textbbox((0, 0), line, font=selected)[2] for line in lines), default=0)
        if widest <= right - left and len(lines) * line_height <= bottom - top:
            break
        selected = font(getattr(selected, "size", min_size) - 2, bold=bold)
        lines = wrap(draw, text, selected, right - left)
    line_height = int(getattr(selected, "size", min_size) * spacing)
    overflow = len(lines) * line_height > bottom - top or any(
        draw.textbbox((0, 0), line, font=selected)[2] > right - left for line in lines
    )
    y = top
    for line in lines:
        draw.text((left, y), line, font=selected, fill=fill)
        y += line_height
    return {
        "box": [left, top, right, bottom],
        "font_size": getattr(selected, "size", min_size),
        "line_count": len(lines),
        "overflow": overflow,
        "bottom": y,
    }


def brand_header(draw: ImageDraw.ImageDraw, *, width: int, label: str, counter: str) -> None:
    draw.rounded_rectangle((64, 56, 114, 106), radius=12, fill=ORANGE)
    draw.text((77, 65), "САП", font=font(15, bold=True), fill=WHITE)
    draw.text((132, 61), "СпецАвтоПортал", font=font(31, bold=True), fill=INK)
    draw.text((132, 98), label.upper(), font=font(19, bold=True), fill=ORANGE)
    counter_width = draw.textbbox((0, 0), counter, font=font(23, bold=True))[2]
    draw.text((width - 64 - counter_width, 70), counter, font=font(23, bold=True), fill=MUTED)


def contact_sheet(images: list[Path], output: Path, *, columns: int, thumb_width: int) -> Path:
    loaded = [Image.open(path).convert("RGB") for path in images]
    thumbs: list[Image.Image] = []
    for source in loaded:
        height = round(source.height * thumb_width / source.width)
        thumbs.append(source.resize((thumb_width, height), Image.Resampling.LANCZOS))
    cell_height = max(image.height for image in thumbs)
    rows = (len(thumbs) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * thumb_width, rows * cell_height), INK)
    for index, thumb in enumerate(thumbs):
        sheet.paste(thumb, ((index % columns) * thumb_width, (index // columns) * cell_height))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, optimize=True)
    return output


def verify_images(paths: list[Path], expected_size: tuple[int, int], layouts: list[dict[str, Any]]) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for path, layout in zip(paths, layouts):
        with Image.open(path) as image:
            size_ok = image.size == expected_size
        files.append({
            "file": path.name,
            "resolution": list(expected_size),
            "resolution_ok": size_ok,
            "text_overflow": any(block.get("overflow") for block in layout.get("text_blocks", [])),
            "safe_margins_ok": layout.get("safe_margins_ok", False),
            "minimum_font_size": min((block.get("font_size", 999) for block in layout.get("text_blocks", [])), default=None),
        })
    return {
        "expected_resolution": list(expected_size),
        "file_count": len(files),
        "files": files,
        "all_resolution_ok": all(row["resolution_ok"] for row in files),
        "all_text_fits": all(not row["text_overflow"] for row in files),
        "all_safe_margins_ok": all(row["safe_margins_ok"] for row in files),
    }
