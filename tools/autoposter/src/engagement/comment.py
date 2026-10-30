"""Draft comments; adapted from Jakeschincariol/instagram-agent-skill (MIT)."""
from __future__ import annotations

import re
from typing import Any

from ..intelligence.common import clean, sentences, tokens
from ..intelligence.repurpose import validate_supported_statement


GENERIC = ("отличный пост", "классный пост", "полностью соглас", "так держать")


def _anchor(text: str) -> str:
    first = sentences(text)[0] if sentences(text) else clean(text)
    words = first.split()
    return " ".join(words[:10]).rstrip(".,:;—-")


def _verified_fact(context: Any) -> tuple[str, dict[str, Any] | None]:
    if not context:
        return "", None
    if isinstance(context, str):
        return "", {"code": "unverified_context", "detail": "Контекст без точного evidence не использован."}
    fact, evidence = clean(context.get("fact")), clean(context.get("evidence"))
    validation = validate_supported_statement(fact, evidence)
    if not validation["supported"]:
        return "", {"code": "unsupported_verified_context", "detail": "Факт не совпадает с предоставленным evidence."}
    return fact, None


def draft_comments(source_post_text: str, account_handle: str, verified_context: Any = None) -> dict[str, Any]:
    post, handle = clean(source_post_text), clean(account_handle).lstrip("@")
    if len(tokens(post)) < 4 or not handle:
        return {"status": "editorial_review_required", "drafts": [], "recommendation": "", "warnings": [{"code": "missing_context"}], "auto_posted": False, "approval_required": True}
    anchor = _anchor(post)
    fact, warning = _verified_fact(verified_context)
    drafts = [
        {"type": "ASK_REAL_QUESTION", "text": f"В части про «{anchor}» какой фактор вы считаете решающим на практике?"},
        {"type": "EXTEND_ONE_LINE", "text": f"Формулировка «{anchor}» задаёт важный вопрос: в каких условиях вывод уже не работает?"},
    ]
    if fact:
        drafts[1] = {"type": "ADD_VERIFIED_CONTEXT", "text": f"К этому можно добавить проверенный контекст: {fact}"}
    warnings = [warning] if warning else []
    for draft in drafts:
        if len(sentences(draft["text"])) > 3 or re.search(r"https?://|www\.", draft["text"], re.I) or any(x in draft["text"].lower() for x in GENERIC):
            warnings.append({"code": "unsafe_comment_draft", "type": draft["type"]})
    return {
        "status": "draft_ready" if not warnings else "draft_ready_with_warnings",
        "account_handle": f"@{handle}", "drafts": drafts,
        "recommendation": "Предпочтителен ASK_REAL_QUESTION: он конкретен и не добавляет непроверенных утверждений.",
        "warnings": warnings, "auto_posted": False, "approval_required": True,
    }
