from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9./%+×xх-]*")
NUMBER_RE = re.compile(r"(?<!\w)\d+(?:[.,]\d+)?(?:\s?(?:%|тонн\w*|млрд|млн|руб\w*|кг|км|т|л))?", re.I)


class IntelligenceDataError(ValueError):
    """Imported advisory data failed deterministic validation."""


def clean(value: Any) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def normalized(value: Any) -> str:
    return re.sub(r"[^a-zа-яё0-9]+", " ", clean(value).lower()).strip()


def tokens(value: Any) -> set[str]:
    return {
        word.lower() for word in WORD_RE.findall(clean(value))
        if len(word) >= 3
    }


def similarity(left: Any, right: Any) -> float:
    left_tokens, right_tokens = tokens(left), tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))


def sentences(value: Any) -> list[str]:
    text = clean(value)
    protected = re.sub(r"\b([A-ZА-ЯЁ])\.([A-ZА-ЯЁ])\.", r"\1§\2§", text)
    return [
        part.replace("§", ".").strip()
        for part in re.split(r"(?<=[.!?])\s+", protected)
        if part.strip()
    ]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def strict_number(value: Any, field: str, row: int, *, required: bool = False) -> float | None:
    if value is None or str(value).strip() == "":
        if required:
            raise IntelligenceDataError(f"row {row}: {field} is required")
        return None
    raw = str(value).strip().replace(" ", "").replace("_", "")
    if not re.fullmatch(r"\d+(?:[.,]\d+)?", raw):
        raise IntelligenceDataError(f"row {row}: {field} must be a nonnegative number, got {value!r}")
    result = float(raw.replace(",", "."))
    if result < 0:
        raise IntelligenceDataError(f"row {row}: {field} cannot be negative")
    return result


def median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2
