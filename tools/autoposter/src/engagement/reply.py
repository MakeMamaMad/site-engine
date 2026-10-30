"""Classify imported comments and prepare safe replies (MIT upstream adaptation)."""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

from ..intelligence.common import clean, normalized, tokens


CATEGORIES = ("KEYWORD", "LEAD", "SUBSTANCE", "QUESTION", "SUPPORT", "NOISE")
NOISE = ("заработок без вложений", "пишите в директ", "подпишись", "идиот", "тупой", "лох")
LEAD = ("цена", "стоимость", "сколько стоит", "купить", "заказать", "нужен", "нужна", "помогите подобрать")
SUPPORT = ("класс", "спасибо", "отлично", "супер", "огонь")


def _category(text: str, keyword: str) -> str:
    low, norm = text.lower(), normalized(text)
    if re.search(r"https?://|www\.", low) or any(x in low for x in NOISE):
        return "NOISE"
    if keyword and norm == normalized(keyword):
        return "KEYWORD"
    if any(x in low for x in LEAD):
        return "LEAD"
    if "?" in text or re.match(r"^(как|что|где|когда|почему|можно ли|какой|какая)\b", low):
        return "QUESTION"
    if len(tokens(text)) >= 8 or re.search(r"\d", text) or any(x in low for x in ("не соглас", "однако", "но ")):
        return "SUBSTANCE"
    if len(tokens(text)) <= 4 or any(x in low for x in SUPPORT) or text.startswith("@"):
        return "SUPPORT"
    return "SUBSTANCE"


def classify_comments(comments: list[dict[str, Any]], *, keyword: str = "", verified_answers: dict[str, str] | None = None) -> dict[str, Any]:
    verified_answers = verified_answers or {}
    rows, counts, prioritized, reel_questions, skipped = [], Counter(), [], [], []
    priority = {"KEYWORD": 0, "LEAD": 1, "SUBSTANCE": 2, "QUESTION": 3}
    for index, item in enumerate(comments):
        text, handle = clean(item.get("text")), clean(item.get("handle") or f"comment_{index + 1}")
        category = _category(text, keyword)
        counts[category] += 1
        row = {"handle": handle, "text": text, "category": category}
        rows.append(row)
        if category in {"NOISE", "SUPPORT"}:
            skipped.append({**row, "reason": "spam_or_hostility" if category == "NOISE" else "low_value_support"})
            continue
        status, suggestion = "draft_ready", ""
        if category == "KEYWORD":
            suggestion = "Спасибо, запрос увидели. Материал отправит редактор после проверки получателя."
        elif category == "LEAD":
            suggestion = "Уточните, пожалуйста, тип техники и задачу — тогда ответ будет предметным."
        elif category == "SUBSTANCE":
            suggestion = "Спасибо за конкретное замечание. Проверим его по источнику перед ответом."
        else:
            answer = clean(verified_answers.get(text))
            if answer:
                suggestion = answer
            else:
                status = "editorial_review_required"
                suggestion = "Ответ требует проверенных данных; не публиковать до редакционной проверки."
            reel_questions.append({"handle": handle, "question": text, "status": status})
        prioritized.append({**row, "reply": suggestion, "status": status, "priority": priority[category]})
    prioritized.sort(key=lambda row: row["priority"])
    return {
        "status": "editorial_review_required" if any(x["status"] == "editorial_review_required" for x in prioritized) else "draft_ready",
        "counts": {name: counts[name] for name in CATEGORIES}, "classified": rows,
        "prioritized_replies": prioritized, "future_reel_questions": reel_questions,
        "skipped": skipped, "auto_replied": False, "approval_required": True,
    }
