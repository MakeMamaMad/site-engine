"""Prepare recipient-specific DM drafts; never send them (MIT upstream adaptation)."""
from __future__ import annotations

from typing import Any

from ..intelligence.common import clean


KINDS = {"resource_request", "existing_conversation", "partnership"}


def prepare_dm(context: dict[str, Any]) -> dict[str, Any]:
    kind = clean(context.get("kind"))
    handle = clean(context.get("handle")).lstrip("@")
    trigger = clean(context.get("trigger"))
    reason = clean(context.get("contact_reason"))
    warnings: list[dict[str, str]] = []
    if kind not in KINDS or not handle or not trigger or not reason:
        return {"status": "editorial_review_required", "message": "", "character_count": 0, "follow_ups": [], "approval_required": True, "sent": False, "warnings": [{"code": "missing_recipient_context"}]}
    name = clean(context.get("name")) or f"@{handle}"
    follow_ups: list[dict[str, Any]] = []
    if kind == "resource_request":
        resource = clean(context.get("resource"))
        if not resource:
            warnings.append({"code": "missing_requested_resource"})
            message = ""
        else:
            message = f"{name}, вы просили материал по теме «{reason}». Вот он: {resource}\n\nЕсли потребуется, уточните тип техники или задачу."
    elif kind == "existing_conversation":
        thread = clean(context.get("conversation_excerpt"))
        value = clean(context.get("value_to_offer"))
        if not thread or not value:
            warnings.append({"code": "missing_conversation_evidence"})
            message = ""
        else:
            message = f"{name}, продолжу нашу тему «{thread}». {value}\n\nПолезно обсудить это подробнее?"
    else:
        proposal, benefit, ask = (clean(context.get(key)) for key in ("proposal", "recipient_benefit", "ask"))
        if not proposal or not benefit or not ask:
            warnings.append({"code": "incomplete_partnership_proposal"})
            message = ""
        else:
            message = f"{name}, пишу по конкретному поводу: {trigger}.\n{proposal}\nДля вас: {benefit}\n{ask}"
    if message:
        new_value = clean(context.get("follow_up_value"))
        if new_value:
            follow_ups.append({"day": 4, "message": f"Добавлю к предложению: {new_value}"})
        follow_ups.append({"day": 10, "message": "Закрою тему, чтобы не отвлекать. Если она станет актуальна, можно вернуться к переписке."})
    return {
        "status": "draft_ready" if message and not warnings else "editorial_review_required",
        "recipient": f"@{handle}", "kind": kind, "message": message,
        "character_count": len(message), "follow_ups": follow_ups[:2],
        "approval_required": True, "sent": False, "warnings": warnings,
    }
