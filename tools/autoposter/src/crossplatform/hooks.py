"""Source-grounded, platform-specific hook/caption packaging.

Builds distinct packaging for YouTube Shorts, Instagram Reels and TikTok from
one approved article. Every factual statement in the output is an exact,
complete source sentence that the owner listed as verified and that passes the
Growth Intelligence factual validator (``validate_supported_statement`` and the
``_safe_hook`` completeness rules). Calls-to-action are fixed non-factual
templates and are labeled as such.

Rewrites (for example storyboard overlays or editor-proposed hooks) are only
validated and reported; anything that is not an exact supported statement is
marked ``editorial_review_required``. Nothing here replaces production
narration, re-renders video, publishes, or calls a paid model.
"""
from __future__ import annotations

import re
from typing import Any

from ..ai.growth_agent import EMPTY_PROMO, SENSITIVE_CLAIM_MARKERS, _semantic_claim_issues
from ..intelligence.common import NUMBER_RE, clean, normalized, sentences, similarity
from ..intelligence.repurpose import MECHANISM_MARKERS, PRACTICAL_MARKERS, _safe_hook, validate_supported_statement


PLATFORMS = ("youtube", "instagram", "tiktok")
TRUNCATION_RE = re.compile(r"(?:\.\.\.|…|\[\s*(?:\.\.\.|…)\s*\])\s*$")
EMOTIVE_MARKERS = tuple(EMPTY_PROMO) + (
    "невероятн", "уникальн", "революц", "шок", "сенсац", "срочно", "вы не поверите", "катастроф", "потрясающ", "гигантск",
    "величествен", "мегапроект", "настоящий", "грандиоз", "колоссальн", "!",
)
# Status reported for an earlier moment ("летом ... оценивали") is still a
# verified fact, but it is a misleading opening line, so hooks avoid it.
DATED_CONTEXT_RE = re.compile(r"^(?:летом|весной|осенью|зимой|ранее|в прошлом|в начале года|прежде)\b", re.I)
LIMITS = {
    "youtube_title": 100,
    "youtube_description": 5000,
    "instagram_caption": 2200,
    "tiktok_caption": 2200,
    "tiktok_caption_target": 300,
}
CTA_TEMPLATES = {
    "youtube": "Полный разбор и ссылка на источник — на spec-avtoportal.ru. Подписывайтесь на канал, чтобы следить за отраслью.",
    "instagram": "Сохраните пост, чтобы вернуться к цифрам. Источник — в подписи.",
    "tiktok": "Как это скажется на ваших рейсах? Напишите в комментариях.",
}
PACKAGING_STRATEGY = {
    "youtube": "Search-oriented: exact source headline as title, the most specific numeric fact as the opening hook, a fact list with the source link in the description.",
    "instagram": "Save-oriented explainer: a practical or mechanism fact as the hook, the verified numbers as a scannable list, source line and save CTA.",
    "tiktok": "Conversation-oriented: the shortest current, complete fact as the spoken/on-screen hook; the caption is only the source headline plus a comment prompt, with no site promotion.",
}


def _is_emotive(text: str) -> list[str]:
    lowered = text.lower()
    return [marker for marker in EMOTIVE_MARKERS if marker in lowered]


def _is_sensitive(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in SENSITIVE_CLAIM_MARKERS)


def evidence_sentences(article: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Return (usable source sentences, truncated sentences excluded)."""
    usable: list[str] = []
    truncated: list[str] = []
    parts = [clean(article.get("title"))] + [clean(article.get(key)) for key in ("summary", "content", "transcript")]
    for part in parts:
        if not part:
            continue
        # Anything after an inline "[...]" marker is an excerpt tail, not evidence.
        head, marker, tail = part.partition("[...]")
        for sentence in sentences(head):
            (truncated if TRUNCATION_RE.search(sentence) else usable).append(sentence)
        if marker:
            truncated.append(clean(marker + tail))
    deduped: list[str] = []
    for sentence in usable:
        if sentence not in deduped:
            deduped.append(sentence)
    return deduped, truncated


def _source_url(article: dict[str, Any]) -> str:
    return clean(article.get("source_url") or article.get("link") or article.get("url"))


def validate_fact(statement: str, evidence: list[str], source_url: str) -> dict[str, Any]:
    text = " ".join(evidence)
    validation = validate_supported_statement(statement, text)
    # Whole-sentence match (punctuation/spacing-insensitive): a fragment of a
    # sentence can drop a condition or qualifier, so it is not accepted.
    exact = next((sentence for sentence in evidence if normalized(sentence) == normalized(statement)), None)
    return {
        "statement": clean(statement),
        "supported": validation["supported"] and exact is not None,
        "complete_source_sentence": exact is not None,
        "exact_source_text": exact,
        "source_url": source_url,
        "validation": validation,
    }


def validate_rewrite(candidate: str, evidence: list[str], source_url: str, *, origin: str) -> dict[str, Any]:
    """Validate an editor/storyboard rewrite. Never auto-approves paraphrase."""
    text = " ".join(evidence)
    statement = clean(candidate)
    validation = validate_supported_statement(statement, text)
    reasons: list[str] = []
    if validation["unsupported_numbers"]:
        reasons.append("unsupported_numbers")
    if not validation["exact_source_sentence"]:
        reasons.append("not_an_exact_source_statement")
    emotive = [m for m in _is_emotive(statement) if m not in text.lower()]
    if emotive:
        reasons.append("unverified_emotional_language")
    semantic = _semantic_claim_issues(statement, evidence)
    reasons.extend(issue["code"] for issue in semantic)
    safe = not reasons
    return {
        "origin": origin,
        "candidate": statement,
        "status": "validated_extractive" if safe else "editorial_review_required",
        "reasons": reasons,
        "unsupported_numbers": validation["unsupported_numbers"],
        "emotive_markers": emotive,
        "semantic_issues": semantic,
        "token_overlap": validation["token_overlap"],
        "source_url": source_url,
        "applied_to_package": False,
    }


def _storyboard_candidates(storyboard: Any) -> list[str]:
    if not storyboard:
        return []
    scenes = storyboard.get("scenes") if isinstance(storyboard, dict) else getattr(storyboard, "scenes", [])
    result = []
    for scene in (scenes or [])[:2]:
        overlay = scene.get("overlay") if isinstance(scene, dict) else getattr(scene, "overlay", "")
        if clean(overlay):
            result.append(clean(overlay))
    return result


def _pick(candidates: list[dict[str, Any]], used: list[str], prefer) -> dict[str, Any] | None:
    ordered = sorted(candidates, key=prefer)
    for fact in ordered:
        if fact["hook"] and not any(similarity(fact["statement"], previous) >= 0.75 for previous in used):
            return fact
    for fact in ordered:
        if fact["hook"]:
            return fact
    return None


def build_platform_packages(article: dict[str, Any], *, storyboard: Any = None, candidate_rewrites: dict[str, list[str]] | None = None) -> dict[str, Any]:
    source_url = _source_url(article)
    title = clean(article.get("title"))
    source_name = clean(article.get("source_name") or article.get("source") or article.get("domain")) or source_url
    approved = clean(article.get("editorial_status")).lower() == "approved"
    evidence, truncated = evidence_sentences(article)
    warnings: list[dict[str, Any]] = []
    if not source_url.startswith(("http://", "https://")):
        warnings.append({"code": "missing_source_url"})
    if truncated:
        warnings.append({"code": "truncated_source_text_excluded", "excluded": truncated,
                         "detail": "Excerpt tails ending in an ellipsis are not used as evidence."})

    supplied = article.get("verified_facts")
    owner_verified = isinstance(supplied, list) and bool(supplied)
    if not owner_verified:
        warnings.append({"code": "facts_not_owner_verified", "detail": "No verified_facts list; packaging requires editorial review."})
        supplied = [s for s in evidence if s != title]

    facts: list[dict[str, Any]] = []
    rejected_facts: list[dict[str, Any]] = []
    for statement in supplied:
        result = validate_fact(statement, evidence, source_url)
        if not result["supported"]:
            reason = "truncated_in_source" if any(clean(statement)[:40] in t for t in truncated) else (
                "unsupported_numbers" if result["validation"]["unsupported_numbers"] else "not_an_exact_complete_source_sentence")
            rejected_facts.append({**result, "reason": reason})
            continue
        result["statement"] = re.sub(r"\s+([.,;:!?])", r"\1", result["exact_source_text"])
        hook, hook_validation, hook_reason = _safe_hook(result["statement"], " ".join(evidence))
        lowered = result["statement"].lower()
        facts.append({
            **result,
            "hook": hook,
            "hook_rejection": hook_reason or None,
            "numeric": bool(NUMBER_RE.search(result["statement"])),
            "practical": any(m in lowered for m in PRACTICAL_MARKERS + MECHANISM_MARKERS),
            "sensitive_regulatory": _is_sensitive(result["statement"]),
            "emotive_markers": _is_emotive(result["statement"]),
            "dated_context": bool(DATED_CONTEXT_RE.search(result["statement"])),
        })
    if rejected_facts:
        warnings.append({"code": "verified_facts_rejected", "count": len(rejected_facts)})

    used: list[str] = []
    packages: dict[str, Any] = {}

    def evidence_entry(fact: dict[str, Any], role: str) -> dict[str, Any]:
        return {"role": role, "statement": fact["statement"], "exact_source_text": fact["exact_source_text"],
                "source_url": source_url, "supported": True}

    def finish(platform: str, hook_fact: dict[str, Any] | None, body: dict[str, Any], evidence_list: list[dict[str, Any]], issues: list[dict[str, Any]]) -> dict[str, Any]:
        reasons = [issue["code"] for issue in issues]
        if hook_fact is None:
            reasons.append("no_safe_hook")
        if not approved:
            reasons.append("source_not_approved")
        if not owner_verified:
            reasons.append("facts_not_owner_verified")
        review = bool({"no_safe_hook", "source_not_approved", "facts_not_owner_verified", "title_exceeds_limit"} & set(reasons))
        sensitive = any(f["sensitive_regulatory"] for f in facts if f["statement"] in {e["statement"] for e in evidence_list})
        if review:
            confidence = "low"
        elif sensitive or reasons:
            confidence = "medium"
        else:
            confidence = "high"
        return {
            "platform": platform,
            "strategy": PACKAGING_STRATEGY[platform],
            "hook": hook_fact["hook"] if hook_fact else None,
            **body,
            "cta": CTA_TEMPLATES[platform],
            "cta_type": "non_factual_template",
            "source_evidence": evidence_list,
            "issues": issues,
            "confidence": confidence,
            "status": "editorial_review_required" if review else "ready_for_owner_review",
            "approval_status": "pending_owner_approval",
            "contains_regulatory_or_sensitive_claim": sensitive,
        }

    neutral = lambda f: (1 if f["emotive_markers"] else 0) + (1 if f["dated_context"] else 0)  # noqa: E731

    # YouTube: most specific numeric fact; exact headline as title.
    yt_hook = _pick(facts, used, lambda f: (neutral(f), not f["numeric"], -len(NUMBER_RE.findall(f["statement"])), len(f["statement"])))
    if yt_hook:
        used.append(yt_hook["statement"])
    issues: list[dict[str, Any]] = []
    yt_title = title
    if len(title) > LIMITS["youtube_title"]:
        issues.append({"code": "title_exceeds_limit", "length": len(title), "limit": LIMITS["youtube_title"],
                       "detail": "Source headline is not truncated automatically; an editor must write a validated title."})
        yt_title = None
    if _is_emotive(title):
        issues.append({"code": "source_headline_emotive", "markers": _is_emotive(title)})
    desc_facts = [f for f in sorted(facts, key=lambda f: (neutral(f), not f["numeric"])) if not f["emotive_markers"]][:3]
    description = "\n".join([f["statement"] for f in desc_facts] + ["", f"Источник: {source_name} — {source_url}", "", CTA_TEMPLATES["youtube"]]).strip()
    yt_evidence = ([evidence_entry(yt_hook, "hook")] if yt_hook else []) + [evidence_entry(f, "description_fact") for f in desc_facts]
    if yt_title:
        yt_evidence.append({"role": "title", "statement": yt_title, "exact_source_text": title, "source_url": source_url, "supported": True})
    packages["youtube"] = finish("youtube", yt_hook, {"title": yt_title, "description": description}, yt_evidence, issues)

    # Instagram: practical/mechanism fact as hook; numbers as a list.
    ig_hook = _pick(facts, used, lambda f: (neutral(f), not f["practical"], f["numeric"], len(f["statement"])))
    if ig_hook:
        used.append(ig_hook["statement"])
    numbers = [f for f in facts if f["numeric"] and not f["emotive_markers"] and (not ig_hook or f["statement"] != ig_hook["statement"])][:4]
    caption_lines = [ig_hook["statement"] if ig_hook else title, ""]
    if numbers:
        caption_lines += ["Цифры из источника:"] + [f"— {f['statement']}" for f in numbers] + [""]
    caption_lines += [f"Источник: {source_name}.", "", CTA_TEMPLATES["instagram"]]
    tags = [t for t in (article.get("hashtags") or []) if re.fullmatch(r"#[\wА-Яа-яЁё]+", str(t))][:5]
    if tags:
        caption_lines += ["", " ".join(tags)]
    ig_caption = "\n".join(caption_lines)
    ig_issues = []
    if len(ig_caption) > LIMITS["instagram_caption"]:
        ig_issues.append({"code": "caption_exceeds_limit", "length": len(ig_caption)})
    ig_evidence = ([evidence_entry(ig_hook, "hook")] if ig_hook else []) + [evidence_entry(f, "caption_fact") for f in numbers]
    packages["instagram"] = finish("instagram", ig_hook, {"caption": ig_caption}, ig_evidence, ig_issues)

    # TikTok: shortest complete fact; one-line caption + comment prompt.
    tt_hook = _pick(facts, used, lambda f: (neutral(f), len(f["statement"])))
    if tt_hook:
        used.append(tt_hook["statement"])
    tt_caption = f"{title}\n{CTA_TEMPLATES['tiktok']}"
    tt_issues = []
    if len(tt_caption) > LIMITS["tiktok_caption_target"]:
        tt_issues.append({"code": "caption_longer_than_target", "length": len(tt_caption), "target": LIMITS["tiktok_caption_target"]})
    tt_evidence = ([evidence_entry(tt_hook, "hook")] if tt_hook else []) + [
        {"role": "caption_headline", "statement": title, "exact_source_text": title, "source_url": source_url, "supported": True}]
    packages["tiktok"] = finish("tiktok", tt_hook, {"caption": tt_caption}, tt_evidence, tt_issues)

    hooks = [packages[p]["hook"] for p in PLATFORMS if packages[p]["hook"]]
    if len(set(hooks)) < len(hooks):
        warnings.append({"code": "hook_reused_across_platforms", "detail": "Fewer distinct safe facts than platforms."})

    rewrites: list[dict[str, Any]] = []
    for candidate in _storyboard_candidates(storyboard):
        rewrites.append(validate_rewrite(candidate, evidence, source_url, origin="storyboard_overlay"))
    for platform, items in (candidate_rewrites or {}).items():
        for candidate in items:
            rewrites.append({**validate_rewrite(candidate, evidence, source_url, origin=f"editor_rewrite:{platform}"), "platform": platform})

    statuses = [packages[p]["status"] for p in PLATFORMS]
    return {
        "schema": 1,
        "module": "cross_platform_hooks",
        "advisory_only": True,
        "production_effect": "none",
        "replaces_production_narration": False,
        "paid_model_calls": 0,
        "source": {
            "title": title,
            "source_url": source_url,
            "source_name": source_name,
            "published_at": clean(article.get("published_at")),
            "article_id": clean(article.get("id") or article.get("article_id")),
            "editorial_status": clean(article.get("editorial_status")) or "not_approved",
            "data_classification": clean(article.get("data_classification")) or "owner_supplied_source",
        },
        "status": "editorial_review_required" if "editorial_review_required" in statuses else "ready_for_owner_review",
        "verified_facts_used": [{k: f[k] for k in ("statement", "exact_source_text", "numeric", "sensitive_regulatory", "emotive_markers", "dated_context", "hook_rejection")} for f in facts],
        "rejected_facts": rejected_facts,
        "packages": packages,
        "rewrite_suggestions": rewrites,
        "warnings": warnings,
    }


def packages_markdown(result: dict[str, Any]) -> str:
    src = result["source"]
    lines = [
        f"# Platform packaging — {src['title']}",
        "",
        f"Source: [{src['source_name']}]({src['source_url']}) · article `{src['article_id'] or '—'}` · "
        f"editorial status `{src['editorial_status']}` · classification `{src['data_classification']}`",
        "",
        f"Overall: **{result['status']}**. Advisory only — production narration and rendered videos are unchanged.",
        "",
    ]
    names = {"youtube": "YouTube Shorts", "instagram": "Instagram Reels", "tiktok": "TikTok"}
    for platform in PLATFORMS:
        pkg = result["packages"][platform]
        lines += [f"## {names[platform]}", "", f"_Strategy:_ {pkg['strategy']}", "",
                  f"- **Hook:** {pkg['hook'] or '— (no safe hook)'}"]
        if platform == "youtube":
            lines += [f"- **Title:** {pkg['title'] or '— (editor required)'}", "- **Description:**", "", "```text", pkg["description"], "```"]
        else:
            lines += ["- **Caption:**", "", "```text", pkg["caption"], "```"]
        lines += [f"- **CTA** (non-factual template): {pkg['cta']}",
                  f"- **Confidence:** {pkg['confidence']} · **Status:** {pkg['status']} · **Approval:** {pkg['approval_status']}",
                  "- **Evidence:**"]
        lines += [f"  - [{e['role']}] «{e['exact_source_text']}»" for e in pkg["source_evidence"]]
        if pkg["issues"]:
            lines += [f"- **Issues:** {', '.join(i['code'] for i in pkg['issues'])}"]
        lines.append("")
    lines += ["## Rewrite suggestions (validated, never auto-applied)", ""]
    if result["rewrite_suggestions"]:
        for row in result["rewrite_suggestions"]:
            lines.append(f"- `{row['status']}` ({row['origin']}): «{row['candidate']}» — {', '.join(row['reasons']) or 'exact source statement'}")
    else:
        lines.append("- None supplied.")
    lines += ["", "## Warnings", ""]
    lines += [f"- `{w['code']}` {w.get('detail', '')}".rstrip() for w in result["warnings"]] or ["- None."]
    if result["rejected_facts"]:
        lines += ["", "## Rejected 'verified' facts", ""]
        lines += [f"- {r['reason']}: «{r['statement']}»" for r in result["rejected_facts"]]
    lines.append("")
    return "\n".join(lines)
