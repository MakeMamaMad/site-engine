"""Optional, source-grounded quality layer for Short Generator v2.

The module deliberately has no network dependency.  It validates AI output and
also provides a deterministic fallback when OpenAI is unavailable.  Nothing in
this file publishes content or changes the existing storyboard JSON schema.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from difflib import SequenceMatcher
from html import unescape
from typing import Any

from .storyboard import Scene, Storyboard, _scene_prompt


GENERIC_OPENERS = (
    "в этом видео",
    "сегодня мы расскажем",
    "сегодня поговорим",
    "давайте разберемся",
    "давайте разберёмся",
    "ни для кого не секрет",
    "как известно",
    "коротко о главном",
    "что известно",
    "факт из новости",
)

PHRASE_REPLACEMENTS = (
    (r"\bследует отметить,? что\b", ""),
    (r"\bнеобходимо подчеркнуть,? что\b", ""),
    (r"\bна сегодняшний день\b", "сейчас"),
    (r"\bосуществляет поставку\b", "поставляет"),
    (r"\bосуществлять перевозку\b", "перевозить"),
    (r"\bв рамках данного\b", "в этом"),
    (r"\bимеет возможность\b", "может"),
    (r"\bявляется важным\b", "важно"),
)

EMPTY_PROMO = (
    "уникальный", "революционный", "невероятный", "лучший на рынке",
    "инновационный прорыв", "меняет правила игры",
)

WEAK_HOOK_OPENERS = ("она ", "он ", "они ", "это ", "также ", "в частности ", "данный ", "данная ")

PRACTICAL_MARKERS = (
    "позволяет", "поможет", "обслужив", "ремонт", "провер", "следует",
    "рекоменду", "расход", "эконом", "интервал", "нагруз", "шины",
    "стоимость владения", "эксплуатац", "маршрут", "документ",
)

SENSITIVE_CLAIM_MARKERS = (
    "запрещ", "обязан", "обязательн", "вступил в силу", "вступит в силу",
    "штраф", "гост", "федеральный закон", "постановлен", "сертифиц",
    "гарантирует", "безопасн", "экономит", "снижает расход", "увеличивает ресурс",
)

RELEVANCE_MARKERS = {
    "regulation": ("закон", "штраф", "регламент", "гост", "постановлен", "правил", "норм"),
    "operations": ("перевоз", "логист", "автопарк", "маршрут", "эксплуатац", "техобслуж", "сервис"),
    "technology": ("двигател", "ось", "шасси", "прицеп", "тягач", "грузовик", "технолог", "шины"),
    "market": ("рынок", "цена", "продаж", "лизинг", "пошлин", "спрос", "стоимост"),
}

STOPWORDS = {
    "это", "как", "что", "для", "или", "при", "его", "она", "они", "уже", "еще", "ещё",
    "также", "после", "перед", "свой", "свои", "новый", "новая", "новые", "может", "будет",
    "который", "которая", "которые", "компания", "представил", "представила",
}

NUMBER_RE = re.compile(r"(?<![\w])\d[\d\s.,–—-]*(?:%|‰|км|кг|т|тонн\w*|л|млн|млрд|руб\w*|евро|лет|год\w*)?", re.IGNORECASE)
QUOTE_RE = re.compile(r"[«\"]([^»\"]{4,})[»\"]")
WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9-]*")


class GrowthAgentError(RuntimeError):
    """A growth storyboard could not be proven against the source item."""


def is_enabled(value: str | None = None) -> bool:
    if value is None:
        import os
        value = os.getenv("GROWTH_AGENT_ENABLED", "0")
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _clean(value: Any) -> str:
    text = unescape(str(value or ""))
    text = re.sub(r"<figure\b[^>]*>.*?</figure>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"(?<=\d)(?=[А-Яа-яЁё])", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _sentences(value: Any) -> list[str]:
    text = _clean(value)
    # Do not split company abbreviations such as M.A. Research into a fake
    # sentence (a common shape in syndicated news summaries).
    protected = re.sub(r"\b([A-ZА-ЯЁ])\.([A-ZА-ЯЁ])\.", r"\1§\2§", text)
    parts = [part.replace("§", ".").strip() for part in re.split(r"(?<=[.!?])\s+", protected)]
    return [part for part in parts if part]


def _source_parts(item: dict[str, Any]) -> list[str]:
    parts = [
        _clean(item.get("title") or item.get("headline") or item.get("name")),
        _clean(item.get("summary") or item.get("description") or item.get("excerpt")),
    ]
    content = _clean(item.get("content"))
    if content and len(re.findall(r"[А-Яа-яЁё]", content)) >= len(content) * 0.25:
        parts.append(content[:12_000])
    source_name = _clean(item.get("source") or item.get("domain"))
    if source_name:
        parts.append(source_name)
    return [part for part in parts if part]


def source_urls(item: dict[str, Any]) -> list[str]:
    values = (
        item.get("site_url"), item.get("link"), item.get("url"),
        item.get("canonical_url"), item.get("source_url"),
    )
    result: list[str] = []
    for value in values:
        url = _clean(value)
        if url.startswith(("http://", "https://")) and url not in result:
            result.append(url)
    return result


def _tokens(value: str) -> set[str]:
    result = set()
    for word in WORD_RE.findall(value.lower()):
        if len(word) < 4 or word in STOPWORDS:
            continue
        result.add(word[:7])
    return result


def _text_similarity(left: str, right: str) -> float:
    left_tokens, right_tokens = _tokens(left), _tokens(right)
    containment = 0.0
    if left_tokens and right_tokens:
        containment = len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))
    return max(SequenceMatcher(None, left.lower(), right.lower()).ratio(), containment)


def _normal_number(value: str) -> str:
    return re.sub(r"[\s.,–—-]+", "", value.lower())


def _supported_numbers(value: str, evidence: str) -> list[str]:
    source_numbers = {_normal_number(x) for x in NUMBER_RE.findall(evidence)}
    return [x for x in NUMBER_RE.findall(value) if _normal_number(x) not in source_numbers]


def normalize_russian_text(value: str) -> tuple[str, list[dict[str, str]]]:
    """Remove common written/AI artefacts without touching names or quantities."""
    original = _clean(value)
    text = original
    findings: list[dict[str, str]] = []
    low = text.lower()
    for opener in GENERIC_OPENERS:
        if low.startswith(opener):
            text = re.sub(rf"^{re.escape(opener)}\s*[:,—-]?\s*", "", text, flags=re.IGNORECASE)
            findings.append({"type": "generic_opener", "value": opener})
            break
    for pattern, replacement in PHRASE_REPLACEMENTS:
        changed = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        if changed != text:
            findings.append({"type": "bureaucratic_phrase", "value": pattern})
            text = changed
    for phrase in EMPTY_PROMO:
        if phrase in text.lower():
            findings.append({"type": "empty_promotion", "value": phrase})
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    text = re.sub(r"\s{2,}", " ", text).strip(" ,;:—-")
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    for sentence in _sentences(text):
        if len(WORD_RE.findall(sentence)) > 22:
            findings.append({"type": "long_sentence", "value": sentence[:120]})
    return text or original, findings


def _shorten(value: str, limit: int = 96) -> str:
    text = _clean(value)
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0]
    return (cut or text[: limit - 1]).rstrip(" ,;:") + "…"


def _spoken_sentence(value: str, max_words: int = 22) -> str:
    text = _clean(value)
    words = WORD_RE.findall(text)
    source_truncated = text.endswith(("...", "…"))
    if len(words) > max_words or source_truncated:
        split = re.split(r"\s+[—;]\s+|(?<=,)\s+", text)
        useful = [part.strip(" ,;:—-") for part in split if len(WORD_RE.findall(part)) >= 4]
        if len(useful) > 1 and len(WORD_RE.findall(useful[0])) <= max_words:
            if source_truncated:
                text = useful[0]
            else:
                combined: list[str] = []
                for part in useful:
                    if len(WORD_RE.findall(", ".join([*combined, part]))) > max_words:
                        break
                    combined.append(part)
                text = ", ".join(combined) if combined else useful[0]
        elif len(words) > max_words:
            match = list(WORD_RE.finditer(text))[max_words - 1]
            text = text[: match.end()].rstrip(" ,;:—-") + "…"
    if text and text[-1] not in ".!?…":
        text += "."
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    return text


def _candidate_supported(candidate: str, evidence: str) -> bool:
    if _supported_numbers(candidate, evidence):
        return False
    candidate_tokens = _tokens(candidate)
    evidence_tokens = _tokens(evidence)
    return len(candidate_tokens & evidence_tokens) >= min(2, max(1, len(candidate_tokens)))


def score_hook(candidate: str, item: dict[str, Any]) -> float:
    words = WORD_RE.findall(candidate)
    evidence = " ".join(_source_parts(item))
    if not candidate or not _candidate_supported(candidate, evidence):
        return 0.0
    score = 40.0
    if 5 <= len(words) <= 13:
        score += 22
    elif len(words) <= 17:
        score += 10
    else:
        score -= min(25, (len(words) - 17) * 2)
    if NUMBER_RE.search(candidate):
        score += 14
    if re.search(r"\b[А-ЯЁA-Z][А-ЯЁA-Z0-9-]{2,}\b", candidate):
        score += 8
    low = candidate.lower()
    score += min(12, sum(4 for markers in RELEVANCE_MARKERS.values() for marker in markers if marker in low))
    if any(low.startswith(opener) for opener in GENERIC_OPENERS):
        score -= 30
    if any(low.startswith(opener) for opener in WEAK_HOOK_OPENERS):
        score -= 28
    if any(phrase in low for phrase in EMPTY_PROMO):
        score -= 25
    return max(0.0, min(100.0, score))


def generate_hook_candidates(item: dict[str, Any], supplied: Iterable[Any] = ()) -> list[dict[str, Any]]:
    """Return three distinct, source-supported alternatives and their scores."""
    title = _clean(item.get("title") or item.get("headline") or item.get("name"))
    summary_sentences = _sentences(item.get("summary") or item.get("description") or item.get("excerpt"))
    raw: list[str] = [_clean(value) for value in supplied if _clean(value)]
    raw.extend([title, *summary_sentences[:3]])
    if title:
        raw.extend((f"Коротко о главном: {title}", f"Что известно: {title}"))
    evidence = " ".join(_source_parts(item))
    candidates: list[str] = []
    for value in raw:
        candidate = _shorten(value.strip(" ."), 96)
        if not candidate or not _candidate_supported(candidate, evidence):
            continue
        if any(_text_similarity(candidate, existing) > 0.9 for existing in candidates):
            continue
        candidates.append(candidate)
    if not candidates and title:
        candidates.append(_shorten(title, 96))
    while candidates and len(candidates) < 3:
        prefix = ("Коротко о главном: ", "Факт из новости: ")[len(candidates) - 1]
        candidates.append(_shorten(prefix + candidates[0], 96))
    scored = [{"text": value, "score": score_hook(value, item)} for value in candidates]
    return sorted(scored, key=lambda row: (-row["score"], len(row["text"])))[:3]


def _source_sentences(item: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for part in _source_parts(item)[:2]:
        values.extend(_sentences(part))
    result: list[str] = []
    for value in values:
        value = _shorten(value, 260)
        low = value.lower()
        if low.startswith(("image:", "изображение:", "пост ")) or "впервые появ" in low:
            continue
        if any(marker in low for marker in ("подробности", "по телефону", "звоните", "ссылка в", "подписывайтесь")):
            continue
        if len(_tokens(value)) >= 2 and value not in result:
            result.append(value)
    return result


def validate_storyboard(board: Storyboard, item: dict[str, Any]) -> dict[str, Any]:
    evidence = " ".join(_source_parts(item))
    evidence_tokens = _tokens(evidence)
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if len(WORD_RE.findall(evidence)) < 8:
        errors.append({"code": "insufficient_source", "detail": "Source has fewer than eight words."})
    if not board.scenes:
        errors.append({"code": "missing_scenes", "detail": "Storyboard has no scenes."})
    elif board.scenes[0].seconds > 3.0:
        errors.append({"code": "late_hook", "detail": f"First scene is {board.scenes[0].seconds:.1f}s."})
    seen_narration: set[str] = set()
    for index, scene in enumerate(board.scenes):
        if scene.id.startswith("cta"):
            continue
        unsupported = _supported_numbers(scene.narration, evidence)
        if unsupported:
            errors.append({"code": "unsupported_number", "scene": scene.id, "values": unsupported})
        for quote in QUOTE_RE.findall(scene.narration):
            if quote.lower() not in evidence.lower():
                errors.append({"code": "unsupported_quote", "scene": scene.id, "value": quote})
        for marker in SENSITIVE_CLAIM_MARKERS:
            if marker in scene.narration.lower() and marker not in evidence.lower():
                errors.append({"code": "unsupported_sensitive_claim", "scene": scene.id, "value": marker})
        overlap = _tokens(scene.narration) & evidence_tokens
        if index > 0 and len(overlap) < 2:
            errors.append({"code": "ungrounded_scene", "scene": scene.id, "detail": scene.narration})
        if any(_text_similarity(scene.narration, previous) > 0.9 for previous in seen_narration):
            errors.append({"code": "repeated_scene", "scene": scene.id})
        seen_narration.add(scene.narration)
        if len(WORD_RE.findall(scene.narration)) > 22:
            warnings.append({"code": "long_sentence", "scene": scene.id})
    unsupported_hook = _supported_numbers(board.hook, evidence)
    if unsupported_hook:
        errors.append({"code": "unsupported_hook_number", "values": unsupported_hook})
    return {"valid": not errors, "errors": errors, "warnings": warnings}


def _caption_data(item: dict[str, Any], hook: str, fact: str, hashtags: list[str]) -> dict[str, str]:
    source_name = _clean(item.get("source") or item.get("domain"))
    urls = source_urls(item)
    site_url = next((url for url in urls if "spec-avtoportal.ru" in url), "https://spec-avtoportal.ru/")
    original_url = next((url for url in urls if "spec-avtoportal.ru" not in url), "")
    tags = " ".join(hashtags[:5])
    attribution = f"Источник: {source_name}." if source_name else ""
    instagram = "\n\n".join(part for part in (
        hook,
        fact,
        attribution,
        "Подробности — по ссылке в профиле.",
        tags,
    ) if part)
    tiktok = "\n\n".join(part for part in (
        hook, fact, attribution, "Разбор — в профиле.", " ".join(hashtags[:4]),
    ) if part)
    youtube = "\n\n".join(part for part in (
        hook,
        fact,
        f"Подробнее: {site_url}",
        f"Первоисточник: {original_url}" if original_url else attribution,
        tags,
    ) if part)
    return {"instagram": instagram, "tiktok": tiktok, "youtube": youtube}


def _default_hashtags(item: dict[str, Any]) -> list[str]:
    haystack = " ".join(_source_parts(item)).lower()
    tags = ["#СпецАвтоПортал", "#коммерческийтранспорт"]
    for marker, tag in (
        ("логист", "#логистика"), ("грузов", "#грузовики"),
        ("прицеп", "#полуприцепы"), ("автопарк", "#автопарк"),
        ("шин", "#грузовыешины"), ("закон", "#транспортноеправо"),
    ):
        if marker in haystack and tag not in tags:
            tags.append(tag)
    return tags[:5]


def build_fallback_storyboard(item: dict[str, Any], *, reason: str = "deterministic") -> Storyboard:
    """Build a useful storyboard using only Russian source sentences."""
    facts = _source_sentences(item)
    if len(WORD_RE.findall(" ".join(facts))) < 8:
        raise GrowthAgentError("insufficient source details for a grounded storyboard")
    hooks = generate_hook_candidates(item)
    if not hooks:
        raise GrowthAgentError("no source-supported hook candidate")
    hook = hooks[0]["text"]
    title = _clean(item.get("title") or item.get("headline") or hook)
    fact_sentences = [
        sentence for sentence in facts
        if sentence.lower().rstrip(".") != title.lower().rstrip(".")
        and _text_similarity(sentence, hook) < 0.88
    ]
    if not fact_sentences:
        fact_sentences = [facts[0]]
    while len(fact_sentences) < 3:
        fact_sentences.append(fact_sentences[-1])
    practical = next(
        (sentence for sentence in fact_sentences if any(marker in sentence.lower() for marker in PRACTICAL_MARKERS)),
        "",
    )
    selected: list[str] = []
    for sentence in [*fact_sentences, practical]:
        if sentence and sentence not in selected:
            selected.append(sentence)
    if not selected:
        raise GrowthAgentError("source does not contain a distinct fact")
    detail = selected[1] if len(selected) > 1 else ""
    takeaway = practical if practical and practical not in selected[:2] else (selected[2] if len(selected) > 2 else "")
    source_name = _clean(item.get("source") or item.get("domain"))
    image = _clean(item.get("image_url") or item.get("image") or item.get("thumbnail"))
    scenes = [
        Scene("hook", 2.8, _shorten(hook, 72), _spoken_sentence(hook, 16), _scene_prompt(title, "hero shot, immediate factual hook"), source_image_url=image),
        Scene("fact", 7.0, "ФАКТ", _spoken_sentence(fact_sentences[0]), _scene_prompt(title, "documentary close-up of the reported event"), source_image_url=image),
    ]
    if detail:
        scenes.append(Scene("context", 6.0, "КОНТЕКСТ", _spoken_sentence(detail), _scene_prompt(title, "wide operational context with fleet and logistics"), source_image_url=image))
    if takeaway:
        scenes.append(Scene("takeaway", 6.0, "ПРАКТИЧЕСКИЙ СМЫСЛ", _spoken_sentence(takeaway), _scene_prompt(title, "practical equipment detail, visibly different camera angle"), source_image_url=image))
    if len(scenes) < 3 and source_name:
        scenes.append(Scene("source", 7.0, "ИСТОЧНИК", _spoken_sentence(f"Данные опубликованы: {source_name}"), _scene_prompt(title, "editorial newsroom context with industrial subject"), source_image_url=image))
    scenes.append(Scene("cta", 4.2, "ПОДРОБНЕЕ В ПРОФИЛЕ", "Подробности — по ссылке в профиле.", _scene_prompt(title, "clean closing hero shot with dark negative space"), source_image_url=image))
    if len(scenes) < 4:
        raise GrowthAgentError("source does not support four distinct storyboard beats")
    hashtags = _default_hashtags(item)
    captions = _caption_data(item, hook, fact_sentences[0], hashtags)
    board = Storyboard(
        version=2,
        format="explainer" if practical else "breaking",
        title=title,
        hook=hook,
        voiceover=" ".join(scene.narration for scene in scenes),
        instagram_caption=captions["instagram"],
        tiktok_caption=captions["tiktok"],
        youtube_title=_shorten(hook, 100),
        youtube_description=captions["youtube"],
        hashtags=hashtags,
        source_urls=source_urls(item),
        scenes=scenes,
    )
    validation = validate_storyboard(board, item)
    if not validation["valid"]:
        raise GrowthAgentError(f"deterministic storyboard failed validation: {validation['errors']}")
    board._growth_report = {  # type: ignore[attr-defined]
        "schema": 1,
        "enabled": True,
        "mode": "deterministic_fallback",
        "reason": reason,
        "hook_candidates": hooks,
        "selected_hook": hook,
        "validation": validation,
        "source_urls": board.source_urls,
        "practical_takeaway_supported": bool(practical),
        "scene_diversity": len({scene.visual_prompt for scene in scenes}) == len(scenes),
    }
    return board


def enhance_storyboard(
    board: Storyboard,
    item: dict[str, Any],
    *,
    supplied_hooks: Iterable[Any] = (),
) -> Storyboard:
    """Humanize, choose a supported hook, format captions and validate AI output."""
    hooks = generate_hook_candidates(item, supplied_hooks)
    if not hooks:
        raise GrowthAgentError("no supported hook candidate")
    body_lines = [scene.narration for scene in board.scenes[1:] if not scene.id.startswith("cta")]
    hook_row = next(
        (
            row for row in hooks
            if all(_text_similarity(row["text"], line) < 0.88 for line in body_lines)
        ),
        hooks[0],
    )
    hook = hook_row["text"]
    humanizer: list[dict[str, Any]] = []
    for scene in board.scenes:
        scene.narration, findings = normalize_russian_text(scene.narration)
        humanizer.extend({"scene": scene.id, **finding} for finding in findings)
    board.scenes[0].seconds = min(3.0, board.scenes[0].seconds)
    board.scenes[0].narration = _spoken_sentence(hook, 16)
    board.scenes[0].overlay = _shorten(hook, 72)
    board.hook = hook
    board.voiceover = " ".join(scene.narration for scene in board.scenes)
    board.source_urls = source_urls(item)
    hashtags = [tag for tag in board.hashtags if str(tag).startswith("#")][:5] or _default_hashtags(item)
    board.hashtags = hashtags
    fact = next((scene.narration for scene in board.scenes[1:] if not scene.id.startswith("cta")), hook)
    captions = _caption_data(item, hook, fact, hashtags)
    board.instagram_caption = captions["instagram"]
    board.tiktok_caption = captions["tiktok"]
    board.youtube_title = _shorten(hook, 100)
    board.youtube_description = captions["youtube"]

    # An AI sometimes repeats the same generic visual direction.  Preserve the
    # subject while making each scene's shot purpose explicit.
    seen_prompts: set[str] = set()
    angles = ("macro mechanical detail", "fleet operations wide shot", "driver or workshop action", "road logistics context")
    for index, scene in enumerate(board.scenes):
        key = re.sub(r"\W+", "", scene.visual_prompt.lower())
        if key in seen_prompts and scene.visual_prompt:
            scene.visual_prompt = f"{scene.visual_prompt} Distinct shot: {angles[index % len(angles)]}."
        seen_prompts.add(re.sub(r"\W+", "", scene.visual_prompt.lower()))

    validation = validate_storyboard(board, item)
    if not validation["valid"]:
        raise GrowthAgentError(f"AI storyboard failed factual validation: {validation['errors']}")
    board._growth_report = {  # type: ignore[attr-defined]
        "schema": 1,
        "enabled": True,
        "mode": "ai_validated",
        "hook_candidates": hooks,
        "selected_hook": hook,
        "validation": validation,
        "humanizer_findings": humanizer,
        "source_urls": board.source_urls,
        "scene_diversity": len({scene.visual_prompt for scene in board.scenes}) == len(board.scenes),
    }
    return board


def growth_report(board: Storyboard) -> dict[str, Any]:
    return getattr(board, "_growth_report", {"schema": 1, "enabled": False})


def mark_legacy_fallback(board: Storyboard, reason: str) -> Storyboard:
    """Make a last-resort legacy fallback explicit in artifacts and manifests."""
    board._growth_report = {  # type: ignore[attr-defined]
        "schema": 1,
        "enabled": True,
        "mode": "legacy_fallback",
        "reason": reason[:800],
        "validation": {"valid": False, "errors": [{"code": "growth_fallback_unavailable", "detail": reason[:800]}], "warnings": []},
        "source_urls": board.source_urls,
    }
    return board


def content_intelligence_score(item: dict[str, Any]) -> tuple[float, list[str]]:
    text = " ".join(_source_parts(item)).lower()
    score = 0.0
    reasons: list[str] = []
    weights = {"regulation": 4.0, "operations": 3.2, "technology": 2.8, "market": 2.5}
    for angle, markers in RELEVANCE_MARKERS.items():
        hits = [marker for marker in markers if marker in text]
        if hits:
            score += weights[angle] + min(2.0, (len(hits) - 1) * 0.5)
            reasons.append(angle)
    if any(marker in text for marker in PRACTICAL_MARKERS):
        score += 3.5
        reasons.append("practical_takeaway")
    if NUMBER_RE.search(text):
        score += 1.0
        reasons.append("specific_evidence")
    return score, reasons


def topic_similarity(left: str, right: str) -> float:
    a, b = _tokens(left), _tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def is_near_duplicate(title: str, previous_titles: Iterable[str], threshold: float = 0.62) -> bool:
    return any(topic_similarity(title, previous) >= threshold for previous in previous_titles if previous)


def recommend_content_plan(items: list[dict[str, Any]], previous_titles: Iterable[str], limit: int = 7) -> list[dict[str, Any]]:
    """Recommendation only; callers must not schedule or publish these rows."""
    previous = list(previous_titles)
    ranked: list[dict[str, Any]] = []
    chosen_titles: list[str] = []
    for item in items:
        title = _clean(item.get("title") or item.get("headline"))
        if not title or is_near_duplicate(title, [*previous, *chosen_titles]):
            continue
        score, reasons = content_intelligence_score(item)
        ranked.append({"id": item.get("id"), "slug": item.get("slug"), "title": title, "score": score, "reasons": reasons})
    ranked.sort(key=lambda row: (-row["score"], row["title"]))
    result: list[dict[str, Any]] = []
    for row in ranked:
        if is_near_duplicate(row["title"], [entry["title"] for entry in result]):
            continue
        result.append(row)
        if len(result) == limit:
            break
    return result
