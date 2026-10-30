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

WEAK_HOOK_OPENERS = (
    "она ", "он ", "они ", "это ", "об этом ", "также ", "в частности ",
    "данный ", "данная ",
)

HOOK_DANGLING_ENDINGS = (
    " и", " но", " а", " для", " с", " из", " что", " который", " которая",
    " которые", " потому что", " поскольку", " при", " по данным",
)
BAD_HOOK_LEADING_WORDS = {"и", "но", "а", "или", "что", "как", "до", "после", "при", "по", "в", "на"}
VAGUE_HOOK_SUBJECTS = {"данные", "система", "компания", "операторы", "производитель"}
VAGUE_HOOK_ENDINGS = {"данные", "важность", "операторам", "показатели", "информация", "решение"}
CONTEXT_DEPENDENT_VERBS = {
    "позволяет", "позволяют", "помогает", "помогают", "планирует", "планируют",
    "может", "могут", "будет", "будут",
}

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

CAUSAL_MARKERS = (
    "из-за", "потому что", "поскольку", "поэтому", "в результате",
    "привёл к", "привела к", "привело к", "привели к", "благодаря",
)
NEGATION_RE = re.compile(r"\b(?:не|нет|ни|без)\b", re.IGNORECASE)
PLANNED_LEGAL_MARKERS = (
    "планирует", "планируют", "планируется", "подготовят", "предложил", "предложила",
    "предложили", "может быть введ", "намерен", "намерены", "ожидается", "проект закона",
)
ENACTED_LEGAL_MARKERS = (
    "вступил в силу", "вступила в силу", "вступили в силу", "действует", "принят закон",
    "приняли закон", "утвержден", "утверждён", "утверждена", "введен", "введён", "введена",
)
ATTRIBUTION_VERBS = {
    "заявил": "заяв", "заявила": "заяв", "заявили": "заяв",
    "сообщил": "сообщ", "сообщила": "сообщ", "сообщили": "сообщ",
    "считает": "счита", "считают": "счита", "прогнозирует": "прогноз", "прогнозируют": "прогноз",
    "предложил": "предлож", "предложила": "предлож", "предложили": "предлож",
    "представил": "представ", "представила": "представ", "представили": "представ",
    "выпустил": "выпуст", "выпустила": "выпуст", "выпустили": "выпуст",
}
NON_MANUFACTURER_ACRONYMS = {
    "ЕС", "ЕЭК", "ВТО", "ГОСТ", "ФЗ", "РФ", "США", "LCV", "OEM", "ИИ", "API",
}

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
MODEL_RE = re.compile(r"\b(?:[A-ZА-ЯЁ]{1,8}[- ]?)?\d[A-Za-zА-Яа-яЁё0-9-]*\b")
MANUFACTURER_RE = re.compile(r"\b[A-ZА-ЯЁ][A-ZА-ЯЁ0-9-]{2,}\b")


class GrowthAgentError(RuntimeError):
    """A growth storyboard could not be proven against the source item."""

    def __init__(self, message: str, report: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.report = report or {
            "schema": 2,
            "enabled": True,
            "status": "rejected",
            "hard_failures": [{"code": "growth_agent_error", "detail": message}],
            "warnings": [],
        }


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


def estimate_spoken_seconds(value: str, words_per_second: float = 2.6) -> float:
    words = WORD_RE.findall(value)
    spoken_characters = sum(len(word) for word in words)
    return max(len(words) / words_per_second, spoken_characters / 10.0)


def _looks_like_verb(word: str) -> bool:
    low = word.lower()
    return bool(re.search(
        r"(?:ал|ала|али|ел|ела|ели|ил|ила|или|ет|ёт|ит|ют|ут|ат|ят|ется|ётся|ются|утся|ится|ятся)$",
        low,
    ))


def _looks_like_adjective(word: str) -> bool:
    return bool(re.search(r"(?:ый|ий|ой|ный|ский|цкий|овый|евый|ивый|чивый|ая|яя|ое|ее|ого|его|ому|ему)$", word.lower()))


def _compact_source_clause(value: str) -> str:
    """Build a short grammatical claim using only ordered source tokens."""
    words = WORD_RE.findall(value)
    prepositions = {"с", "для", "при", "по", "о", "об", "в", "на", "из", "к", "перед", "до", "после"}
    for verb_index in range(1, min(4, len(words))):
        if not _looks_like_verb(words[verb_index]):
            continue
        if words[verb_index].lower() in CONTEXT_DEPENDENT_VERBS:
            continue
        subject_index = next(
            (index for index in range(verb_index - 1, -1, -1) if words[index].lower() not in {"не", "ни"} and not _looks_like_adjective(words[index])),
            None,
        )
        if subject_index is None:
            continue
        if any(not _looks_like_adjective(word) for word in words[:subject_index]):
            continue
        object_index = None
        for index in range(verb_index + 1, len(words)):
            if words[index].lower() in prepositions:
                break
            is_infinitive = bool(re.search(r"(?:ать|ять|еть|ить|уть|оть)$", words[index].lower()))
            if not _looks_like_adjective(words[index]) and not is_infinitive:
                object_index = index
                break
        if object_index is None:
            continue
        middle = [word for word in words[subject_index + 1:verb_index] if word.lower() in {"не", "ни"}]
        return " ".join([words[subject_index], *middle, words[verb_index], words[object_index]])
    return ""


def _is_complete_statement(value: str) -> bool:
    text = _clean(value).rstrip()
    low = text.lower().rstrip(".!?")
    words = WORD_RE.findall(text)
    if not 3 <= len(words) <= 22:
        return False
    if text.endswith(("...", "…", ",", ";", ":", "—", "-")):
        return False
    return not any(low.endswith(ending) for ending in HOOK_DANGLING_ENDINGS)


def _hook_complete(value: str) -> bool:
    text = _clean(value).rstrip()
    words = WORD_RE.findall(text)
    short_clause = (
        len(words) == 2
        and _looks_like_verb(words[-1])
        and not text.endswith(("...", "…", ",", ";", ":", "—", "-"))
    )
    has_action = any(_looks_like_verb(word) for word in words)
    good_opening = (
        bool(words)
        and words[0].lower() not in (BAD_HOOK_LEADING_WORDS | VAGUE_HOOK_SUBJECTS)
        and words[-1].lower() not in VAGUE_HOOK_ENDINGS
        and not _looks_like_verb(words[0])
        and not any(text.lower().startswith(opener) for opener in WEAK_HOOK_OPENERS)
    )
    return good_opening and has_action and (_is_complete_statement(value) or short_clause) and estimate_spoken_seconds(value) <= 2.8


def _evidence_sentences(item: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for part in _source_parts(item)[:3]:
        for sentence in _sentences(part):
            sentence = _clean(sentence)
            if sentence and sentence not in result:
                result.append(sentence)
    return result


def _best_evidence(claim: str, evidence_sentences: list[str]) -> tuple[str, float]:
    if not evidence_sentences:
        return "", 0.0
    ranked = sorted(
        ((sentence, _text_similarity(claim, sentence)) for sentence in evidence_sentences),
        key=lambda pair: pair[1],
        reverse=True,
    )
    return ranked[0]


def _legal_status(value: str) -> str:
    low = value.lower()
    if any(marker in low for marker in ENACTED_LEGAL_MARKERS):
        return "enacted"
    if any(marker in low for marker in PLANNED_LEGAL_MARKERS):
        return "planned"
    return "unspecified"


def _causal_signature(value: str) -> tuple[str, set[str], set[str]] | None:
    low = value.lower()
    for marker in CAUSAL_MARKERS:
        position = low.find(marker)
        if position >= 0:
            return marker, _tokens(value[:position]), _tokens(value[position + len(marker):])
    return None


def _causal_issue(claim: str, evidence_sentences: list[str]) -> dict[str, Any] | None:
    signature = _causal_signature(claim)
    if not signature:
        return None
    marker, left, right = signature
    source_signatures = [
        (sentence, source_signature)
        for sentence in evidence_sentences
        if (source_signature := _causal_signature(sentence)) is not None
    ]
    if not source_signatures:
        return {"code": "unsupported_causal_claim", "value": marker}
    for sentence, (_, source_left, source_right) in source_signatures:
        direct = _set_overlap(left, source_left) + _set_overlap(right, source_right)
        inverted = _set_overlap(left, source_right) + _set_overlap(right, source_left)
        if inverted >= 1.2 and inverted > direct + 0.35:
            return {"code": "inverted_causal_relationship", "value": marker, "source": sentence}
        if direct >= 1.0:
            return None
    return {"code": "causal_relationship_mismatch", "value": marker}


def _set_overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / min(len(left), len(right))


def _attribution_relations(value: str) -> list[tuple[str, str]]:
    words = WORD_RE.findall(value)
    relations: list[tuple[str, str]] = []
    for index, word in enumerate(words):
        stem = ATTRIBUTION_VERBS.get(word.lower())
        if not stem:
            continue
        # The nearest noun/name is a safer attribution key than the whole
        # preceding clause (which often includes unrelated hook wording).
        actor_words = words[max(0, index - 1):index]
        actor = " ".join(actor_words).lower()
        if actor:
            relations.append((actor, stem))
    match = re.search(r"\bпо данным\s+([^,.;:]{2,60})", value, flags=re.IGNORECASE)
    if match:
        relations.append((_clean(match.group(1)).lower(), "data"))
    return relations


def _attribution_issue(claim: str, evidence_sentences: list[str]) -> dict[str, Any] | None:
    for actor, stem in _attribution_relations(claim):
        actor_tokens = _tokens(actor)
        supported = False
        for sentence in evidence_sentences:
            source_low = sentence.lower()
            actor_supported = (
                bool(actor_tokens) and _set_overlap(actor_tokens, _tokens(sentence)) >= 0.6
            ) or bool(re.search(rf"(?<!\w){re.escape(actor)}(?!\w)", source_low))
            verb_supported = stem == "data" and "по данным" in source_low or stem != "data" and stem in source_low
            if actor_supported and verb_supported:
                supported = True
                break
        if not supported:
            return {"code": "incorrect_attribution", "actor": actor, "relation": stem}
    return None


def _entity_model_pairs(value: str) -> set[tuple[str, str]]:
    manufacturers = {
        match.group(0).upper()
        for match in MANUFACTURER_RE.finditer(value)
        if match.group(0).upper() not in NON_MANUFACTURER_ACRONYMS
    }
    models = {match.group(0).upper().replace(" ", "") for match in MODEL_RE.finditer(value)}
    return {(manufacturer, model) for manufacturer in manufacturers for model in models}


def _entity_model_issue(claim: str, evidence_sentences: list[str]) -> dict[str, Any] | None:
    claim_pairs = _entity_model_pairs(claim)
    if not claim_pairs:
        return None
    source_pairs = set().union(*(_entity_model_pairs(sentence) for sentence in evidence_sentences))
    all_source = " ".join(evidence_sentences).upper().replace(" ", "")
    for manufacturer, model in claim_pairs:
        if (manufacturer, model) not in source_pairs and manufacturer in all_source and model in all_source:
            return {"code": "manufacturer_model_mixup", "manufacturer": manufacturer, "model": model}
    return None


def _semantic_claim_issues(claim: str, evidence_sentences: list[str]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    best, similarity = _best_evidence(claim, evidence_sentences)
    if best and similarity >= 0.42:
        claim_negated = bool(NEGATION_RE.search(claim))
        source_negated = bool(NEGATION_RE.search(best))
        if claim_negated != source_negated:
            issues.append({
                "code": "negation_mismatch",
                "claim_negated": claim_negated,
                "source": best,
            })
        claim_status, source_status = _legal_status(claim), _legal_status(best)
        if claim_status != "unspecified" and source_status != "unspecified" and claim_status != source_status:
            issues.append({
                "code": "legal_status_mismatch",
                "claim_status": claim_status,
                "source_status": source_status,
                "source": best,
            })
    for detector in (_causal_issue, _attribution_issue, _entity_model_issue):
        issue = detector(claim, evidence_sentences)
        if issue:
            issues.append(issue)
    return issues


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
    if not candidate or not _hook_complete(candidate) or not _candidate_supported(candidate, evidence):
        return 0.0
    score = 40.0
    if 5 <= len(words) <= 8:
        score += 22
    elif len(words) <= 10:
        score += 8
    else:
        score -= min(25, (len(words) - 10) * 4)
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


def _hook_variants(value: Any) -> list[str]:
    text = _clean(value).strip(" .")
    variants = [text]
    for part in re.split(r"\s+[—–-]\s+|:\s+|,\s+", text):
        part = part.strip(" .,:;—–-")
        if part and part != text:
            variants.append(part)
    for part in list(variants):
        compact = _compact_source_clause(part)
        if compact and compact != part:
            variants.append(compact)
    result: list[str] = []
    for candidate in variants:
        if _hook_complete(candidate) and candidate not in result:
            result.append(candidate)
    return result


def generate_hook_candidates(item: dict[str, Any], supplied: Iterable[Any] = ()) -> list[dict[str, Any]]:
    """Return up to three complete, source-supported hooks that fit three seconds."""
    title = _clean(item.get("title") or item.get("headline") or item.get("name"))
    summary_sentences = _sentences(item.get("summary") or item.get("description") or item.get("excerpt"))
    raw: list[str] = []
    for value in [*supplied, title, *summary_sentences[:5]]:
        low = _clean(value).lower()
        if low.startswith(("пост ", "image:", "изображение:")) or "впервые появ" in low:
            continue
        raw.extend(_hook_variants(value))
    evidence = " ".join(_source_parts(item))
    candidates: list[str] = []
    for value in raw:
        candidate = _clean(value).strip(" .")
        if not candidate or not _candidate_supported(candidate, evidence):
            continue
        if any(_text_similarity(candidate, existing) > 0.9 for existing in candidates):
            continue
        candidates.append(candidate)
    scored = [
        {
            "text": value,
            "score": score_hook(value, item),
            "spoken_seconds": round(estimate_spoken_seconds(value), 2),
        }
        for value in candidates
        if score_hook(value, item) > 0
    ]
    return sorted(scored, key=lambda row: (-row["score"], row["spoken_seconds"], len(row["text"])))[:3]


def _source_sentences(item: dict[str, Any]) -> list[str]:
    values: list[str] = []
    summary = _clean(item.get("summary") or item.get("description") or item.get("excerpt"))
    if summary:
        values.extend(_sentences(summary))
    content = _clean(item.get("content"))
    if content and len(re.findall(r"[А-Яа-яЁё]", content)) >= len(content) * 0.25:
        values.extend(_sentences(content[:12_000]))
    result: list[str] = []
    for value in values:
        value = _clean(value)
        low = value.lower()
        if low.startswith(("image:", "изображение:", "пост ")) or "впервые появ" in low:
            continue
        if low.startswith(("что ", "кто ", "зачем ")):
            continue
        if any(marker in low for marker in (
            "подробности", "по телефону", "звоните", "ссылка в", "подписывайтесь",
            "читайте", "смотрите", "главные тезисы", "в нашем обзоре",
        )):
            continue
        spoken = _spoken_sentence(value)
        if not _is_complete_statement(spoken):
            continue
        if not 6 <= len(WORD_RE.findall(spoken)) <= 22:
            continue
        if any(_text_similarity(spoken, previous) > 0.84 for previous in result):
            continue
        result.append(spoken)
    return result


def assess_source_quality(item: dict[str, Any]) -> dict[str, Any]:
    """Measure whether an item can support a useful source-only short."""
    facts = _source_sentences(item)
    hard_failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if len(facts) < 2:
        hard_failures.append({
            "code": "insufficient_source_depth",
            "detail": f"Need at least two distinct factual beats; found {len(facts)}.",
        })
    elif len(facts) == 2:
        warnings.append({"code": "limited_source_depth", "detail": "Only two distinct factual beats are available."})
    practical_count = sum(any(marker in fact.lower() for marker in PRACTICAL_MARKERS) for fact in facts)
    specific_count = sum(bool(NUMBER_RE.search(fact)) for fact in facts)
    score = len(facts) * 2.0 + practical_count * 1.5 + specific_count * 0.75
    return {
        "status": "rejected" if hard_failures else ("approved_with_warnings" if warnings else "approved"),
        "hard_failures": hard_failures,
        "warnings": warnings,
        "facts": facts,
        "score": score,
        "practical_facts": practical_count,
    }


def validate_storyboard(
    board: Storyboard,
    item: dict[str, Any],
    *,
    check_presentation: bool = True,
) -> dict[str, Any]:
    evidence = " ".join(_source_parts(item))
    evidence_tokens = _tokens(evidence)
    evidence_sentences = _evidence_sentences(item)
    hard_failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    source_quality = assess_source_quality(item)
    hard_failures.extend(source_quality["hard_failures"])
    warnings.extend(source_quality["warnings"])
    if not board.scenes:
        hard_failures.append({"code": "missing_scenes", "detail": "Storyboard has no scenes."})
    elif check_presentation:
        first = board.scenes[0]
        hook_seconds = estimate_spoken_seconds(board.hook)
        if not _hook_complete(board.hook):
            hard_failures.append({"code": "incomplete_or_oversized_hook", "detail": board.hook})
        if first.seconds > 3.0:
            hard_failures.append({"code": "late_hook", "detail": f"First scene is {first.seconds:.1f}s."})
        if hook_seconds + 0.15 > first.seconds:
            hard_failures.append({
                "code": "hook_timing_overflow",
                "detail": f"Hook needs about {hook_seconds:.2f}s but scene allows {first.seconds:.2f}s.",
            })
        if _text_similarity(first.overlay, board.hook) < 0.8:
            hard_failures.append({"code": "hook_not_in_first_frame", "detail": first.overlay})
        if _text_similarity(first.narration, board.hook) < 0.85:
            hard_failures.append({"code": "hook_narration_mismatch", "detail": first.narration})
        title = _clean(item.get("title") or item.get("headline"))
        if len(WORD_RE.findall(title)) > 10 and _text_similarity(board.hook, title) > 0.9:
            hard_failures.append({"code": "long_headline_used_as_hook", "detail": board.hook})
    seen_narration: set[str] = set()
    for index, scene in enumerate(board.scenes):
        is_cta = scene.id.startswith("cta")
        unsupported = _supported_numbers(scene.narration, evidence)
        if unsupported:
            hard_failures.append({"code": "unsupported_number", "scene": scene.id, "values": unsupported})
        for quote in QUOTE_RE.findall(scene.narration):
            if quote.lower() not in evidence.lower():
                hard_failures.append({"code": "unsupported_quote", "scene": scene.id, "value": quote})
        for marker in SENSITIVE_CLAIM_MARKERS:
            if marker in scene.narration.lower() and marker not in evidence.lower():
                hard_failures.append({"code": "unsupported_sensitive_claim", "scene": scene.id, "value": marker})
        for issue in _semantic_claim_issues(scene.narration, evidence_sentences):
            hard_failures.append({"scene": scene.id, **issue})
        overlap = _tokens(scene.narration) & evidence_tokens
        if not is_cta and index > 0 and len(overlap) < 2:
            hard_failures.append({"code": "ungrounded_scene", "scene": scene.id, "detail": scene.narration})
        if not is_cta and any(_text_similarity(scene.narration, previous) > 0.84 for previous in seen_narration):
            hard_failures.append({"code": "repeated_scene", "scene": scene.id})
        if not is_cta:
            seen_narration.add(scene.narration)
        if len(WORD_RE.findall(scene.narration)) > 22:
            warnings.append({"code": "long_sentence", "scene": scene.id})
        if len(_tokens(scene.narration)) < 2:
            warnings.append({"code": "low_information_scene", "scene": scene.id})
    unsupported_hook = _supported_numbers(board.hook, evidence)
    if unsupported_hook:
        hard_failures.append({"code": "unsupported_hook_number", "values": unsupported_hook})
    status = "rejected" if hard_failures else ("approved_with_warnings" if warnings else "approved")
    return {
        "valid": not hard_failures,
        "status": status,
        "hard_failures": hard_failures,
        "errors": hard_failures,
        "warnings": warnings,
        "source_quality": {
            key: value for key, value in source_quality.items() if key != "facts"
        },
    }


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
    source_quality = assess_source_quality(item)
    if source_quality["hard_failures"]:
        report = {
            "schema": 2,
            "enabled": True,
            "status": "rejected",
            "mode": "deterministic_fallback",
            "reason": reason,
            "hard_failures": source_quality["hard_failures"],
            "warnings": source_quality["warnings"],
            "source_quality": {key: value for key, value in source_quality.items() if key != "facts"},
            "source_urls": source_urls(item),
        }
        raise GrowthAgentError("insufficient source depth for a grounded storyboard", report)
    facts = source_quality["facts"]
    hooks = generate_hook_candidates(item)
    if not hooks:
        raise GrowthAgentError("no complete source-supported hook fits the opening duration")
    hook_row: dict[str, Any] | None = None
    fact_sentences: list[str] = []
    for candidate in hooks:
        remaining = [fact for fact in facts if _text_similarity(fact, candidate["text"]) < 0.8]
        if len(remaining) >= 2:
            hook_row = candidate
            fact_sentences = remaining[:3]
            break
    if hook_row is None:
        raise GrowthAgentError("source cannot support a distinct hook plus two factual beats")
    hook = str(hook_row["text"])
    title = _clean(item.get("title") or item.get("headline") or hook)
    image = _clean(item.get("image_url") or item.get("image") or item.get("thumbnail"))
    hook_seconds = min(3.0, max(2.4, estimate_spoken_seconds(hook) + 0.25))
    scenes = [Scene(
        "hook",
        hook_seconds,
        hook,
        _spoken_sentence(hook, 10),
        _scene_prompt(title, "hero shot, immediate factual hook"),
        source_image_url=image,
    )]
    angles = (
        "documentary close-up of the reported event",
        "wide operational context with fleet and logistics",
        "practical equipment detail, visibly different camera angle",
    )
    overlays = ("КЛЮЧЕВОЙ ФАКТ", "ДЕТАЛИ", "ЧТО ЕЩЁ ВАЖНО")
    for index, fact in enumerate(fact_sentences):
        practical = any(marker in fact.lower() for marker in PRACTICAL_MARKERS)
        overlay = "ДЛЯ ЭКСПЛУАТАЦИИ" if practical else overlays[index]
        scenes.append(Scene(
            f"fact-{index + 1}",
            max(5.2, min(7.5, estimate_spoken_seconds(fact) + 0.5)),
            overlay,
            fact,
            _scene_prompt(title, angles[index]),
            source_image_url=image,
        ))
    scenes.append(Scene("cta", 4.2, "ПОДРОБНЕЕ В ПРОФИЛЕ", "Подробности — по ссылке в профиле.", _scene_prompt(title, "clean closing hero shot with dark negative space"), source_image_url=image))
    hashtags = _default_hashtags(item)
    captions = _caption_data(item, hook, fact_sentences[0], hashtags)
    board = Storyboard(
        version=2,
        format="explainer" if source_quality["practical_facts"] else "breaking",
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
        raise GrowthAgentError(
            f"deterministic storyboard failed validation: {validation['hard_failures']}",
            {
                "schema": 2,
                "enabled": True,
                "status": "rejected",
                "mode": "deterministic_fallback",
                "reason": reason,
                "hook_candidates": hooks,
                "selected_hook": hook,
                "validation": validation,
                "hard_failures": validation["hard_failures"],
                "warnings": validation["warnings"],
                "source_urls": board.source_urls,
            },
        )
    board._growth_report = {  # type: ignore[attr-defined]
        "schema": 2,
        "enabled": True,
        "status": validation["status"],
        "mode": "deterministic_fallback",
        "reason": reason,
        "hook_candidates": hooks,
        "selected_hook": hook,
        "validation": validation,
        "hard_failures": validation["hard_failures"],
        "warnings": validation["warnings"],
        "source_urls": board.source_urls,
        "content_beats": len(fact_sentences),
        "source_quality": {key: value for key, value in source_quality.items() if key != "facts"},
        "practical_takeaway_supported": bool(source_quality["practical_facts"]),
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
        None,
    )
    if hook_row is None:
        raise GrowthAgentError("no complete hook remains distinct from the factual beats")
    hook = hook_row["text"]
    humanizer: list[dict[str, Any]] = []
    for scene in board.scenes:
        scene.narration, findings = normalize_russian_text(scene.narration)
        humanizer.extend({"scene": scene.id, **finding} for finding in findings)
    board.scenes[0].seconds = min(3.0, max(2.4, estimate_spoken_seconds(hook) + 0.25))
    board.scenes[0].narration = _spoken_sentence(hook, 10)
    board.scenes[0].overlay = hook
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
        raise GrowthAgentError(
            f"AI storyboard failed validation: {validation['hard_failures']}",
            {
                "schema": 2,
                "enabled": True,
                "status": "rejected",
                "mode": "ai_validated",
                "hook_candidates": hooks,
                "selected_hook": hook,
                "validation": validation,
                "hard_failures": validation["hard_failures"],
                "warnings": validation["warnings"],
                "source_urls": board.source_urls,
            },
        )
    board._growth_report = {  # type: ignore[attr-defined]
        "schema": 2,
        "enabled": True,
        "status": validation["status"],
        "mode": "ai_validated",
        "hook_candidates": hooks,
        "selected_hook": hook,
        "validation": validation,
        "hard_failures": validation["hard_failures"],
        "warnings": validation["warnings"],
        "humanizer_findings": humanizer,
        "source_urls": board.source_urls,
        "scene_diversity": len({scene.visual_prompt for scene in board.scenes}) == len(board.scenes),
    }
    return board


def growth_report(board: Storyboard) -> dict[str, Any]:
    return getattr(board, "_growth_report", {"schema": 1, "enabled": False})


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
