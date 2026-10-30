"""Source-grounded Instagram Stories planning and deterministic rendering."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from ..intelligence.common import clean
from ..intelligence.repurpose import build_repurposing_package
from .carousel import _evidence, _source_dict, usable_claims, validate_editorial_rewrite
from .design import INK, ORANGE, WHITE, approved_local_images, contact_sheet, draw_text_block, editorial_background, font, verify_images


WIDTH, HEIGHT = 1080, 1920
SAFE_TOP, SAFE_BOTTOM = 250, 1600
SIDE_MARGIN = 86


def build_story_sequence(
    source: dict[str, Any], *, audience_question: str = "", editorial_goal: str = "website_visit",
    approved_images: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    adapted = _source_dict(source)
    repurpose = build_repurposing_package(adapted)
    claims = usable_claims(repurpose["extraction"]["claims"])
    if len(claims) < 3:
        return {
            "schema": 1, "module": "ig-story-adaptation", "status": "insufficient_source",
            "advisory_only": True, "frames": [], "approval_required": True,
            "warnings": [{"code": "thin_source", "detail": "At least three distinct exact source sentences are required for a meaningful Story sequence."}],
            "source": repurpose["source"],
        }
    editorial = adapted.get("editorial_evidence")
    if not isinstance(editorial, dict) or len(editorial.get("items") or []) < 4:
        return {
            "schema": 1, "module": "ig-story-adaptation", "status": "editorial_review_required",
            "advisory_only": True, "frames": [], "approval_required": True,
            "warnings": [{"code": "no_validated_shortening_map", "detail": "Conversational Story copy requires explicit editorial mappings to exact evidence."}],
            "source": repurpose["source"],
        }
    images, image_warnings = approved_local_images(approved_images)
    selected = list(editorial["items"][:4])
    frames: list[dict[str, Any]] = []
    layouts = ("hook", "question", "practical", "action")
    for index, item in enumerate(selected, 1):
        role = "hook" if index == 1 else "interaction" if index == len(selected) else "middle"
        combined_validation = {
            "headline": validate_editorial_rewrite(item["story_headline"], item, "story_headline"),
            "body": validate_editorial_rewrite(item["story_body"], item, "story_body"),
        }
        combined_validation["supported"] = combined_validation["headline"]["supported"] and combined_validation["body"]["supported"]
        frames.append({
            "number": index,
            "role": role,
            "layout": layouts[index - 1],
            "headline": item["story_headline"],
            "body": item["story_body"],
            "evidence": [_evidence(item, adapted)],
            "factual_validation": combined_validation,
        })
    frames[-1]["manual_sticker_instruction"] = {
        "sticker": "link",
        "placement": "Добавить вручную в Instagram по центру ниже основного текста, внутри зоны y=1100–1450.",
        "destination": adapted["source_url"],
        "static_preview_notice": "Стикер не изображён на PNG и не является функциональным элементом превью.",
    }
    for index, frame in enumerate(frames, 1):
        frame["number"] = index
        frame["counter"] = f"{index}/{len(frames)}"
        frame["source_url"] = adapted["source_url"]
        frame["alt_text"] = (
            f"Кадр {index} из {len(frames)} Stories СпецАвтоПортала. "
            f"Заголовок: {frame['headline']}. Текст: {frame['body']}"
        )
    return {
        "schema": 1,
        "module": "ig-story-adaptation",
        "status": "ready_for_editorial_review",
        "advisory_only": True,
        "publishing_invoked": False,
        "messages_sent": False,
        "source": repurpose["source"],
        "editorial_goal": editorial_goal,
        "audience_question": clean(audience_question),
        "frames": frames,
        "attribution_manifest": {
            "canonical_url": adapted["source_url"],
            "original_source_url": adapted.get("original_source_url") or "",
            "terminology_reference_url": editorial["terminology_reference_url"],
            "terminology_review": editorial["terminology"],
            "source_name": adapted.get("source_name") or "СпецАвтоПортал",
            "data_classification": adapted.get("data_classification") or "owner_supplied_source",
            "approved_images_used": images,
            "visual_method": "approved local article images with readability overlay" if images else "brand graphics only; no generated or fabricated vehicle photography",
        },
        "warnings": image_warnings,
        "approval_required": True,
    }


def _render_frame(frame: dict[str, Any], output: Path, approved_image: str | None = None) -> dict[str, Any]:
    image = editorial_background((WIDTH, HEIGHT), approved_image if frame["role"] != "interaction" else None, dark=True)
    draw = ImageDraw.Draw(image)
    draw.ellipse((690, 210, 1250, 770), fill=(35, 41, 49))
    draw.ellipse((-260, 1300, 360, 1920), fill=(31, 36, 43))
    draw.rectangle((0, 0, 24, HEIGHT), fill=ORANGE)
    draw.text((SIDE_MARGIN, 278), "СпецАвтоПортал", font=font(31, bold=True), fill=WHITE)
    draw.text((SIDE_MARGIN, 326), "STORIES · ПРЕВЬЮ", font=font(20, bold=True), fill=ORANGE)
    counter_width = draw.textbbox((0, 0), frame["counter"], font=font(24, bold=True))[2]
    draw.text((WIDTH - SIDE_MARGIN - counter_width, 290), frame["counter"], font=font(24, bold=True), fill=(167, 174, 183))
    draw.rectangle((SIDE_MARGIN, 425, SIDE_MARGIN + 160, 437), fill=ORANGE)
    if frame["layout"] == "question":
        draw.rounded_rectangle((SIDE_MARGIN - 20, 740, WIDTH - SIDE_MARGIN + 20, 1260), radius=36, outline=(64, 72, 84), width=5)
    elif frame["layout"] == "action":
        draw.rounded_rectangle((SIDE_MARGIN - 24, 452, WIDTH - SIDE_MARGIN + 24, 1300), radius=44, fill=(35, 41, 49), outline=ORANGE, width=5)
    headline = draw_text_block(
        draw, frame["headline"], (SIDE_MARGIN, 500, WIDTH - SIDE_MARGIN, 760),
        max_size=72 if frame["layout"] == "hook" else 62, min_size=40, bold=True, fill=ORANGE if frame["layout"] == "hook" else WHITE,
    )
    if frame["layout"] == "practical":
        body_font = font(43)
        lines = frame["body"].splitlines()
        y = 820
        for line in lines:
            draw.ellipse((SIDE_MARGIN, y + 15, SIDE_MARGIN + 18, y + 33), fill=ORANGE)
            draw.text((SIDE_MARGIN + 42, y), line, font=body_font, fill=(224, 228, 232))
            y += 112
        body = {
            "box": [SIDE_MARGIN, 820, WIDTH - SIDE_MARGIN, 1280],
            "font_size": 43,
            "line_count": len(lines),
            "overflow": y > 1280,
            "bottom": y,
        }
    else:
        body = draw_text_block(
            draw, frame["body"], (SIDE_MARGIN, 820, WIDTH - SIDE_MARGIN, 1280),
            max_size=52, min_size=34, bold=False, fill=(224, 228, 232), spacing=1.28,
        )
    if frame["role"] == "interaction":
        draw.text((SIDE_MARGIN, 1390), "Редактор добавляет Link sticker вручную", font=font(27, bold=True), fill=ORANGE)
        draw.text((SIDE_MARGIN, 1435), "Статическое превью не имитирует работающий стикер", font=font(23), fill=(167, 174, 183))
    draw.text((SIDE_MARGIN, 1522), "Источник: spec-avtoportal.ru", font=font(23), fill=(167, 174, 183))
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, optimize=True)
    return {
        "text_blocks": [headline, body],
        "safe_margins_ok": headline["box"][1] >= SAFE_TOP and body["bottom"] <= SAFE_BOTTOM,
        "safe_zone": [SIDE_MARGIN, SAFE_TOP, WIDTH - SIDE_MARGIN, SAFE_BOTTOM],
    }


def render_story_sequence(package: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    if package.get("status") != "ready_for_editorial_review":
        return {"status": "not_rendered", "reason": package.get("status"), "files": []}
    frame_dir = output_dir / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    for stale in frame_dir.glob("frame_*.png"):
        stale.unlink()
    paths: list[Path] = []
    layouts: list[dict[str, Any]] = []
    approved = package["attribution_manifest"].get("approved_images_used") or []
    for index, frame in enumerate(package["frames"]):
        path = frame_dir / f"frame_{frame['number']:02d}.png"
        image_path = approved[index % len(approved)]["path"] if approved else None
        layouts.append(_render_frame(frame, path, image_path))
        paths.append(path)
    contact = contact_sheet(paths, output_dir / "contact_sheet.png", columns=3, thumb_width=360)
    qa = verify_images(paths, (WIDTH, HEIGHT), layouts)
    qa.update({"contact_sheet": contact.name, "safe_zone": [SIDE_MARGIN, SAFE_TOP, WIDTH - SIDE_MARGIN, SAFE_BOTTOM], "minimum_readable_font_target": 32})
    return {"status": "rendered", "files": [str(path) for path in paths], "contact_sheet": str(contact), "qa": qa}
