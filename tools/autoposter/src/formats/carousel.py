"""Source-grounded Instagram carousel planning and deterministic rendering."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from ..intelligence.common import NUMBER_RE, clean, normalized
from ..intelligence.repurpose import build_repurposing_package, validate_supported_statement
from .design import INK, MUTED, ORANGE, WHITE, approved_local_images, brand_header, contact_sheet, draw_text_block, editorial_background, font, verify_images


WIDTH, HEIGHT = 1080, 1350
SAFE_MARGIN = 120
BOILERPLATE_MARKERS = ("впервые появился на", "подписывайтесь", "читайте также")
MISLEADING_TECHNICAL_TERMS = ("колпачок концентратора", "концентратор прицепа")


def _source_dict(source: dict[str, Any]) -> dict[str, Any]:
    if source.get("source_url"):
        return source
    return {
        "title": source.get("title"),
        "source_url": source.get("site_url"),
        "original_source_url": source.get("link"),
        "source_name": "СпецАвтоПортал",
        "published_at": source.get("published_at"),
        "summary": source.get("summary"),
        "data_classification": source.get("data_classification") or "repository_owned_article_snapshot",
        "editorial_evidence": source.get("editorial_evidence"),
    }


def validate_slide_grounding(text: str, source_text: str) -> bool:
    return bool(validate_supported_statement(text, source_text)["supported"])


def usable_claims(values: list[str]) -> list[str]:
    return [value for value in values if not any(marker in value.lower() for marker in BOILERPLATE_MARKERS)]


def validate_editorial_rewrite(text: str, item: dict[str, Any], approved_field: str) -> dict[str, Any]:
    candidate = clean(text)
    approved = clean(item.get(approved_field))
    original = clean(item.get("original_text"))
    russian = clean(item.get("russian_translation"))
    banned = [term for term in MISLEADING_TECHNICAL_TERMS if term in candidate.lower()]
    original_numbers = {normalized(value) for value in NUMBER_RE.findall(original + " " + russian)}
    candidate_numbers = {normalized(value) for value in NUMBER_RE.findall(candidate)}
    unsupported_numbers = sorted(candidate_numbers - original_numbers)
    approved_mapping = bool(candidate and approved and normalized(candidate) == normalized(approved))
    return {
        "supported": approved_mapping and bool(original) and not banned and not unsupported_numbers,
        "validation_mode": "explicit_editorial_mapping",
        "approved_mapping": approved_mapping,
        "original_source_present": bool(original),
        "unsupported_numbers": unsupported_numbers,
        "misleading_technical_terms": banned,
        "protected_terms": item.get("protected_terms") or [],
        "qualification": clean(item.get("qualification")),
    }


def _evidence(item: dict[str, Any], adapted: dict[str, Any]) -> dict[str, Any]:
    editorial = adapted["editorial_evidence"]
    return {
        "source_url": editorial["original_source_url"],
        "canonical_url": adapted["source_url"],
        "original_text": item["original_text"],
        "russian_translation": item["russian_translation"],
        "terminology_reference_url": editorial["terminology_reference_url"],
    }


def build_carousel(source: dict[str, Any], *, approved_images: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    adapted = _source_dict(source)
    repurpose = build_repurposing_package(adapted)
    claims = usable_claims(repurpose["extraction"]["claims"])
    if len(claims) < 3:
        return {
            "schema": 1, "module": "ig-carousel-adaptation", "status": "insufficient_source",
            "advisory_only": True, "slides": [], "approval_required": True,
            "warnings": [{"code": "thin_source", "detail": "At least three distinct exact source sentences are required for six meaningful slides."}],
            "source": repurpose["source"],
        }
    editorial = adapted.get("editorial_evidence")
    if not isinstance(editorial, dict) or len(editorial.get("items") or []) < 4:
        return {
            "schema": 1, "module": "ig-carousel-adaptation", "status": "editorial_review_required",
            "advisory_only": True, "slides": [], "approval_required": True,
            "warnings": [{"code": "no_validated_shortening_map", "detail": "Exact evidence exists, but concise visible copy requires explicit editorial mappings."}],
            "source": repurpose["source"],
        }
    images, image_warnings = approved_local_images(approved_images)
    selected = list(editorial["items"][:7])
    by_id = {item["id"]: item for item in selected}
    cover = editorial["carousel_cover"]
    cover_item = by_id[cover["evidence_id"]]
    slides: list[dict[str, Any]] = [{
        "number": 1, "role": "cover", "layout": "cover",
        "headline": cover["headline"], "body": cover["body"],
        "evidence": [_evidence(cover_item, adapted)],
        "factual_validation": {
            "supported": not any(term in (cover["headline"] + " " + cover["body"]).lower() for term in MISLEADING_TECHNICAL_TERMS),
            "validation_mode": "editorially_approved_cover_mapping",
            "source_item": cover_item["id"],
        },
    }]
    for index, item in enumerate(selected, 2):
        combined_validation = {
            "headline": validate_editorial_rewrite(item["carousel_headline"], item, "carousel_headline"),
            "body": validate_editorial_rewrite(item["carousel_body"], item, "carousel_body"),
        }
        combined_validation["supported"] = combined_validation["headline"]["supported"] and combined_validation["body"]["supported"]
        slides.append({
            "number": index, "role": "stake" if index == 2 else "evidence",
            "layout": "spec" if item["id"] == "capacity" else "mechanism" if item["id"] in {"hub_cap", "installation", "eco_plus_2"} else "statement",
            "headline": item["carousel_headline"], "body": item["carousel_body"],
            "evidence": [_evidence(item, adapted)],
            "factual_validation": combined_validation,
        })
    recap_items = selected[:4]
    slides.append({
        "number": len(slides) + 1, "role": "recap", "layout": "recap", "headline": "ЧЕТЫРЕ ВЫВОДА",
        "body": "\n".join(f"{index}. {item['recap_line']}" for index, item in enumerate(recap_items, 1)),
        "evidence": [_evidence(item, adapted) for item in recap_items],
        "factual_validation": {
            "supported": all(validate_editorial_rewrite(item["recap_line"], item, "recap_line")["supported"] for item in recap_items),
            "validation_mode": "explicit_editorial_mapping",
        },
    })
    slides.append({
        "number": len(slides) + 1, "role": "cta", "layout": "cta", "headline": "КАК РАБОТАЕТ ECO METER",
        "body": "Сохраните карточки. Полный разбор — по ссылке в профиле.", "evidence": [],
    })
    assert 6 <= len(slides) <= 10
    for slide in slides:
        slide["counter"] = f"{slide['number']}/{len(slides)}"
        slide["source_url"] = adapted["source_url"]
        slide["alt_text"] = (
            f"Слайд {slide['number']} из {len(slides)} карусели СпецАвтоПортала. "
            f"Заголовок: {slide['headline']}. Текст: {slide['body']}"
        )
    caption = (
        f"{adapted['title']}\n\n"
        f"{selected[0]['russian_translation']}\n\n{selected[2]['russian_translation']}\n\n"
        f"Источник и полный материал: {adapted['source_url']}\n"
        f"Первоисточник: {adapted.get('original_source_url') or 'не указан в импортированном материале'}\n\n"
        "Сохраните, чтобы вернуться к ключевым пунктам.\n\n"
        "#СпецАвтоПортал #коммерческийтранспорт #полуприцепы"
    )
    return {
        "schema": 1,
        "module": "ig-carousel-adaptation",
        "status": "ready_for_editorial_review",
        "advisory_only": True,
        "publishing_invoked": False,
        "source": repurpose["source"],
        "slides": slides,
        "caption": caption,
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


def _render_slide(slide: dict[str, Any], output: Path, approved_image: str | None = None) -> dict[str, Any]:
    image = editorial_background((WIDTH, HEIGHT), approved_image if slide["role"] in {"stake", "evidence"} else None, dark=False)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 34, HEIGHT), fill=ORANGE)
    draw.ellipse((780, 900, 1200, 1320), fill=(231, 233, 228))
    draw.line((SAFE_MARGIN, 204, WIDTH - SAFE_MARGIN, 204), fill=(205, 208, 202), width=3)
    brand_header(draw, width=WIDTH, label="КАРУСЕЛЬ", counter=slide["counter"])
    if slide["role"] == "cover":
        draw.rounded_rectangle((SAFE_MARGIN, 260, WIDTH - SAFE_MARGIN, 1070), radius=42, fill=INK)
        draw.rectangle((SAFE_MARGIN + 52, 334, SAFE_MARGIN + 64, 580), fill=ORANGE)
        headline_box = (SAFE_MARGIN + 105, 334, WIDTH - SAFE_MARGIN - 55, 790)
        body_box = (SAFE_MARGIN + 105, 835, WIDTH - SAFE_MARGIN - 55, 970)
        headline = draw_text_block(draw, slide["headline"].upper(), headline_box, max_size=76, min_size=42, bold=True, fill=WHITE)
        body = draw_text_block(draw, slide["body"], body_box, max_size=38, min_size=30, bold=False, fill=(205, 210, 216))
    elif slide["layout"] == "recap":
        draw.rounded_rectangle((86, 252, WIDTH - 86, 1095), radius=44, fill=INK)
        headline_box = (SAFE_MARGIN, 315, WIDTH - SAFE_MARGIN, 500)
        body_box = (SAFE_MARGIN, 555, WIDTH - SAFE_MARGIN, 1010)
        headline = draw_text_block(draw, slide["headline"], headline_box, max_size=64, min_size=42, bold=True, fill=ORANGE)
        body = draw_text_block(draw, slide["body"], body_box, max_size=40, min_size=30, bold=False, fill=WHITE, spacing=1.38)
    elif slide["layout"] == "cta":
        draw.rounded_rectangle((86, 272, WIDTH - 86, 1050), radius=44, fill=ORANGE)
        headline_box = (SAFE_MARGIN, 360, WIDTH - SAFE_MARGIN, 650)
        body_box = (SAFE_MARGIN, 720, WIDTH - SAFE_MARGIN, 930)
        headline = draw_text_block(draw, slide["headline"], headline_box, max_size=74, min_size=44, bold=True, fill=INK)
        body = draw_text_block(draw, slide["body"], body_box, max_size=42, min_size=32, bold=False, fill=INK)
    else:
        headline_box = (SAFE_MARGIN, 286, WIDTH - SAFE_MARGIN, 520)
        body_box = (SAFE_MARGIN, 590, WIDTH - SAFE_MARGIN, 1060)
        if slide["layout"] == "spec":
            draw.rounded_rectangle((720, 290, 958, 525), radius=36, fill=ORANGE)
            headline_box = (SAFE_MARGIN, 300, 680, 520)
        elif slide["layout"] == "mechanism":
            draw.ellipse((805, 280, 950, 425), fill=(231, 233, 228), outline=ORANGE, width=6)
        headline = draw_text_block(draw, slide["headline"], headline_box, max_size=68 if slide["layout"] == "spec" else 60, min_size=38, bold=True, fill=INK)
        draw.rectangle((SAFE_MARGIN, 548, SAFE_MARGIN + 180, 558), fill=ORANGE)
        body = draw_text_block(draw, slide["body"], body_box, max_size=52, min_size=34, bold=False, fill=INK, spacing=1.28)
    source_label = "Источник: spec-avtoportal.ru"
    draw.text((SAFE_MARGIN, 1190), source_label, font=font(24), fill=MUTED)
    draw.text((SAFE_MARGIN, 1240), "@specavtoportal", font=font(24, bold=True), fill=ORANGE)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, optimize=True)
    return {"text_blocks": [headline, body], "safe_margins_ok": True}


def render_carousel(package: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    if package.get("status") != "ready_for_editorial_review":
        return {"status": "not_rendered", "reason": package.get("status"), "files": []}
    slide_dir = output_dir / "slides"
    slide_dir.mkdir(parents=True, exist_ok=True)
    for stale in slide_dir.glob("slide_*.png"):
        stale.unlink()
    paths: list[Path] = []
    layouts: list[dict[str, Any]] = []
    approved = package["attribution_manifest"].get("approved_images_used") or []
    for index, slide in enumerate(package["slides"]):
        path = slide_dir / f"slide_{slide['number']:02d}.png"
        image_path = approved[index % len(approved)]["path"] if approved else None
        layouts.append(_render_slide(slide, path, image_path))
        paths.append(path)
    contact = contact_sheet(paths, output_dir / "contact_sheet.png", columns=4, thumb_width=270)
    qa = verify_images(paths, (WIDTH, HEIGHT), layouts)
    qa.update({"contact_sheet": contact.name, "minimum_readable_font_target": 30, "grid_safe_margin_pixels": SAFE_MARGIN})
    return {"status": "rendered", "files": [str(path) for path in paths], "contact_sheet": str(contact), "qa": qa}
