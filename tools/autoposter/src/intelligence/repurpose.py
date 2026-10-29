"""Source-grounded extraction and advisory repurposing."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from .common import NUMBER_RE, IntelligenceDataError, clean, normalized, sentences, similarity, tokens


MECHANISM_MARKERS = (
    "работает", "позволяет", "за счёт", "за счет", "фиксирует", "измеряет", "рассчитывает",
    "передаёт", "передает", "записывает", "определяет", "срабатывает", "механизм",
)
PRACTICAL_MARKERS = (
    "следует", "нужно", "необходимо", "рекоменду", "провер", "учитывать", "планировать",
    "перед рейсом", "техобслуж", "обслужив", "ремонт", "контролировать",
)
PROMO_MARKERS = ("подписывайтесь", "читайте на сайте", "ссылка в профиле", "звоните", "купить сейчас")
QUOTE_RE = re.compile(r"[«\"]([^»\"]{8,})[»\"]")


def _source_text(source: dict[str, Any]) -> str:
    return " ".join(
        clean(source.get(key))
        for key in ("summary", "content", "transcript")
        if clean(source.get(key))
    )


def _source_url(source: dict[str, Any]) -> str:
    url = clean(source.get("source_url") or source.get("url") or source.get("link") or source.get("site_url"))
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise IntelligenceDataError("repurposing source requires an absolute source_url")
    return url


def validate_supported_statement(statement: str, source_text: str) -> dict[str, Any]:
    statement_clean = clean(statement)
    evidence = clean(source_text)
    statement_numbers = {normalized(value) for value in NUMBER_RE.findall(statement_clean)}
    source_numbers = {normalized(value) for value in NUMBER_RE.findall(evidence)}
    unsupported_numbers = sorted(statement_numbers - source_numbers)
    exact = normalized(statement_clean) in normalized(evidence)
    overlap = similarity(statement_clean, evidence)
    # Advisory generation is deliberately extractive. Token overlap is kept as
    # a diagnostic, but never turns a paraphrase (or an inverted relationship)
    # into an approved fact.
    supported = bool(statement_clean) and not unsupported_numbers and exact
    return {
        "supported": supported,
        "exact_source_sentence": exact,
        "token_overlap": round(overlap, 3),
        "unsupported_numbers": unsupported_numbers,
    }


def _distinct(values: list[str], threshold: float = 0.82) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and not any(similarity(value, previous) >= threshold for previous in result):
            result.append(value)
    return result


def _safe_hook(sentence: str, source_text: str) -> tuple[str, dict[str, Any], str]:
    """Return an exact, complete source sentence or explain why it is unsafe.

    This intentionally does not summarize or truncate. A deterministic cutter
    cannot know whether a removed condition, attribution, cause or number
    changes the claim, so long evidence remains evidence rather than a hook.
    """
    candidate = clean(sentence)
    empty_validation = validate_supported_statement("", source_text)
    if not candidate:
        return "", empty_validation, "empty_candidate"
    if len(candidate) > 92 or len(candidate.split()) > 14:
        return "", empty_validation, "source_sentence_exceeds_hook_limit"
    if candidate.endswith((",", ":", ";", "—", "-")):
        return "", empty_validation, "incomplete_clause"
    if re.search(r"\b(?:и|но|а|или|что|чтобы|если|когда|поскольку|для|при|с|в|на)$", candidate, re.I):
        return "", empty_validation, "incomplete_clause"
    if re.match(r"^(?:если|когда|пока|поскольку|хотя|при условии)\b", candidate, re.I) and "," not in candidate:
        return "", empty_validation, "incomplete_clause"
    validation = validate_supported_statement(candidate, source_text)
    if not validation["supported"]:
        return "", validation, "final_hook_not_exactly_supported"
    return candidate, validation, ""


def extract_source_material(source: dict[str, Any]) -> dict[str, Any]:
    title = clean(source.get("title"))
    if not title:
        raise IntelligenceDataError("repurposing source requires title")
    url = _source_url(source)
    text = _source_text(source)
    if not text:
        raise IntelligenceDataError("repurposing source requires summary, content or transcript")
    factual_sentences = _distinct([
        sentence for sentence in sentences(text)
        if len(tokens(sentence)) >= 4 and not any(marker in sentence.lower() for marker in PROMO_MARKERS)
    ])
    claims = factual_sentences
    numbered = [sentence for sentence in factual_sentences if NUMBER_RE.search(sentence)]
    mechanisms = [sentence for sentence in factual_sentences if any(marker in sentence.lower() for marker in MECHANISM_MARKERS)]
    practical = [sentence for sentence in factual_sentences if any(marker in sentence.lower() for marker in PRACTICAL_MARKERS)]
    quotes: list[dict[str, str]] = []
    for sentence in factual_sentences:
        for quote in QUOTE_RE.findall(sentence):
            prefix = sentence.split(quote, 1)[0].rstrip(' «"')
            attributed = bool(re.search(r"\b(?:заявил[аи]?|сообщил[аи]?|отметил[аи]?|по словам)\b", prefix, re.I))
            quotes.append({
                "quote": clean(quote),
                "attribution_context": prefix if attributed else "",
                "attribution_status": "explicit" if attributed else "missing",
                "source_sentence": sentence,
            })
    return {
        "title": title,
        "source_url": url,
        "source_name": clean(source.get("source_name") or source.get("source") or source.get("domain")),
        "published_at": clean(source.get("published_at") or source.get("date")),
        "data_classification": clean(source.get("data_classification")) or "owner_supplied_source",
        "claims": claims,
        "numbers_and_specifications": numbered,
        "mechanisms": mechanisms,
        "practical_recommendations": practical,
        "quotable_statements": quotes,
        "counts": {
            "claims": len(claims),
            "numbers_and_specifications": len(numbered),
            "mechanisms": len(mechanisms),
            "practical_recommendations": len(practical),
            "quotable_statements": len(quotes),
        },
        "source_text": text,
    }


def build_repurposing_package(source: dict[str, Any]) -> dict[str, Any]:
    extraction = extract_source_material(source)
    claims = extraction["claims"]
    warnings: list[dict[str, Any]] = []
    if len(claims) < 3:
        warnings.append({
            "code": "thin_source",
            "detail": f"Only {len(claims)} distinct factual sentences; no multi-format package was generated.",
        })
        return {
            "schema": 1,
            "module": "ig-repurpose-adaptation",
            "status": "insufficient_source",
            "advisory_only": True,
            "source": {key: extraction[key] for key in ("title", "source_url", "source_name", "published_at", "data_classification")},
            "extraction": {key: value for key, value in extraction.items() if key not in {"source_text"}},
            "reel_concepts": [],
            "carousel_outlines": [],
            "story_concepts": [],
            "warnings": warnings,
        }

    candidates = _distinct(extraction["mechanisms"] + extraction["practical_recommendations"] + claims)
    reels: list[dict[str, Any]] = []
    used_evidence: list[str] = []
    hook_rejections: list[dict[str, Any]] = []
    for sentence in candidates:
        if any(similarity(sentence, previous) >= 0.75 for previous in used_evidence):
            continue
        hook, hook_validation, rejection_reason = _safe_hook(sentence, extraction["source_text"])
        if not hook:
            hook_rejections.append({
                "reason": rejection_reason,
                "source_evidence": {"source_url": extraction["source_url"], "exact_text": sentence},
            })
            continue
        if len(reels) < 2:
            reels.append({
                "angle": "mechanism" if sentence in extraction["mechanisms"] else "practical" if sentence in extraction["practical_recommendations"] else "verified_claim",
                "suggested_hook": hook,
                "core_claim": sentence,
                "caption_draft": f"{sentence}\n\nИсточник: {extraction['source_name'] or extraction['source_url']}.",
                "source_evidence": [{"source_url": extraction["source_url"], "exact_text": sentence}],
                "factual_validation": hook_validation,
            })
        used_evidence.append(sentence)

    carousels: list[dict[str, Any]] = []
    outline_evidence = _distinct(extraction["numbers_and_specifications"] + extraction["mechanisms"] + extraction["practical_recommendations"])
    if len(outline_evidence) >= 3:
        carousels.append({
            "title": f"{extraction['title']}: подтверждённые детали",
            "slides": [
                {"slide": 1, "role": "cover", "text": extraction["title"]},
                *[
                    {"slide": index + 2, "role": "evidence", "text": sentence, "source_url": extraction["source_url"]}
                    for index, sentence in enumerate(outline_evidence[:4])
                ],
                {"slide": min(6, len(outline_evidence) + 2), "role": "source", "text": f"Источник: {extraction['source_name'] or extraction['source_url']}"},
            ],
            "source_evidence": outline_evidence[:4],
        })

    stories: list[dict[str, Any]] = []
    for quote in extraction["quotable_statements"]:
        if quote["attribution_status"] == "explicit":
            stories.append({
                "type": "attributed_quote",
                "text": quote["quote"],
                "attribution": quote["attribution_context"],
                "source_url": extraction["source_url"],
            })
    if extraction["numbers_and_specifications"]:
        stories.append({
            "type": "specification_card",
            "text": extraction["numbers_and_specifications"][0],
            "source_url": extraction["source_url"],
        })
    if not reels:
        warnings.append({"code": "no_safe_reel_hook", "detail": "Facts were extracted, but none formed a complete short hook."})
    if hook_rejections:
        warnings.append({
            "code": "unsafe_hook_candidates_rejected",
            "detail": f"{len(hook_rejections)} source sentences stayed as evidence because no exact, complete short hook was available.",
        })
    if not carousels:
        warnings.append({"code": "carousel_not_justified", "detail": "Fewer than three distinct mechanisms, specifications or practical points."})
    return {
        "schema": 1,
        "module": "ig-repurpose-adaptation",
        "status": "ready_with_warnings" if warnings else "ready",
        "advisory_only": True,
        "scheduling_effect": "none",
        "source": {key: extraction[key] for key in ("title", "source_url", "source_name", "published_at", "data_classification")},
        "extraction": {key: value for key, value in extraction.items() if key not in {"source_text"}},
        "reel_concepts": reels,
        "carousel_outlines": carousels,
        "story_concepts": stories[:2],
        "hook_rejections": hook_rejections,
        "warnings": warnings,
        "limitations": [
            "Every generated claim is traceable to exact imported source text.",
            "The package is advisory and does not schedule, publish or multiply a thin source into repetitive posts.",
        ],
    }
