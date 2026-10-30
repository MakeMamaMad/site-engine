"""Manual-dataset viral pattern analysis; no browsing or scraping."""
from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .common import IntelligenceDataError, clean, median, normalized, strict_number


REQUIRED_FIELDS = ("account", "source_url", "views", "account_median_views", "hook", "dataset_label")
FORMULA_PATTERNS = (
    ("number_first", "Цифра в первой строке", re.compile(r"^\s*\d|\b\d+(?:[.,]\d+)?\s*(?:%|тонн|км|руб)", re.I)),
    ("negative_command", "Запрет или ошибка", re.compile(r"^(?:не|никогда не|перестаньте|хватит)\b", re.I)),
    ("question", "Практический вопрос", re.compile(r"\?|^(?:почему|зачем|как|что будет)", re.I)),
    ("consequence", "Последствие для эксплуатации", re.compile(r"\b(?:если|иначе|привед[её]т|оберн[её]тся|что изменится)\b", re.I)),
    ("myth_reversal", "Разворот мифа", re.compile(r"\b(?:миф|на самом деле|ошибочно считают|не означает)\b", re.I)),
    ("comparison", "Сравнение", re.compile(r"\b(?:против|или|лучше|хуже|сравн)\b", re.I)),
)

RUSSIAN_TEMPLATES = {
    "number_first": "[Подтверждённая цифра] — что она меняет для перевозчика",
    "negative_command": "Не принимайте решение до проверки [подтверждённого параметра]",
    "question": "Почему [подтверждённый механизм] важен для автопарка?",
    "consequence": "Что изменится для перевозчика, если [подтверждённое условие]",
    "myth_reversal": "Распространённый миф о [теме] — и что говорит источник",
    "comparison": "[Вариант A] или [вариант B]: сравниваем только подтверждённые параметры",
    "unclassified": "Начните с самого конкретного подтверждённого факта источника",
}


def classify_hook_formula(hook: str, supplied: str = "") -> tuple[str, str]:
    explicit = clean(supplied).lower().replace(" ", "_")
    if explicit:
        name = next((name for formula_id, name, _ in FORMULA_PATTERNS if formula_id == explicit), explicit)
        return explicit, name
    for formula_id, name, pattern in FORMULA_PATTERNS:
        if pattern.search(hook):
            return formula_id, name
    return "unclassified", "Не классифицировано"


def load_viral_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".json":
        raw = json.loads(path.read_text(encoding="utf-8"))
        rows = raw.get("rows", raw) if isinstance(raw, dict) else raw
        if not isinstance(rows, list):
            raise IntelligenceDataError("viral JSON must contain a list or a rows list")
        return [dict(row) for row in rows if isinstance(row, dict)]
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _validate_row(raw: dict[str, Any], row_number: int) -> dict[str, Any]:
    missing = [field for field in REQUIRED_FIELDS if clean(raw.get(field)) == ""]
    if missing:
        raise IntelligenceDataError(f"row {row_number}: missing required fields: {', '.join(missing)}")
    account = clean(raw["account"])
    if not account.startswith("@") or not re.fullmatch(r"@[\w.-]{2,64}", account, re.UNICODE):
        raise IntelligenceDataError(f"row {row_number}: invalid account handle {account!r}")
    source_url = clean(raw["source_url"])
    parsed = urlparse(source_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise IntelligenceDataError(f"row {row_number}: source_url must be an absolute HTTP(S) URL")
    views = strict_number(raw.get("views"), "views", row_number, required=True)
    baseline = strict_number(raw.get("account_median_views"), "account_median_views", row_number, required=True)
    assert views is not None and baseline is not None
    if not views.is_integer() or not baseline.is_integer():
        raise IntelligenceDataError(f"row {row_number}: views and account_median_views must be whole counts")
    if views <= 0:
        raise IntelligenceDataError(f"row {row_number}: views must be greater than zero")
    if baseline <= 0:
        raise IntelligenceDataError(f"row {row_number}: account_median_views must be greater than zero")
    length = strict_number(raw.get("length_seconds"), "length_seconds", row_number)
    if length is not None and not 1 <= length <= 300:
        raise IntelligenceDataError(f"row {row_number}: length_seconds must be between 1 and 300")
    hook = clean(raw["hook"])
    if len(hook.split()) < 2:
        raise IntelligenceDataError(f"row {row_number}: hook is too short")
    formula_id, formula_name = classify_hook_formula(hook, clean(raw.get("hook_formula")))
    return {
        "account": account,
        "source_url": source_url,
        "dataset_label": clean(raw["dataset_label"]),
        "captured_at": clean(raw.get("captured_at")),
        "views": int(views),
        "account_median_views": int(baseline),
        "outlier_multiple": round(views / baseline, 3),
        "hook": hook,
        "on_screen": clean(raw.get("on_screen")),
        "length_seconds": length,
        "cta": clean(raw.get("cta")),
        "hook_formula": formula_id,
        "hook_formula_name": formula_name,
    }


def analyze_viral_patterns(rows: list[dict[str, Any]], *, minimum_pattern_samples: int = 3) -> dict[str, Any]:
    validated: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    seen_hooks: set[tuple[str, str]] = set()
    for index, raw in enumerate(rows, 2):
        row = _validate_row(raw, index)
        hook_key = (row["account"].lower(), normalized(row["hook"]))
        if row["source_url"] in seen_urls or hook_key in seen_hooks:
            warnings.append({"code": "duplicate_example_ignored", "row": index, "source_url": row["source_url"]})
            continue
        seen_urls.add(row["source_url"])
        seen_hooks.add(hook_key)
        validated.append(row)
    if not validated:
        raise IntelligenceDataError("viral dataset has no usable unique examples")
    ranked = sorted(validated, key=lambda row: (-row["outlier_multiple"], row["source_url"]))
    third = max(1, len(ranked) // 3)
    top_urls = {row["source_url"] for row in ranked[:third]}
    bottom_urls = {row["source_url"] for row in ranked[-third:]}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in ranked:
        grouped[row["hook_formula"]].append(row)
    patterns: list[dict[str, Any]] = []
    for formula_id, examples in grouped.items():
        accounts = {row["account"] for row in examples}
        multiples = [row["outlier_multiple"] for row in examples]
        top_count = sum(row["source_url"] in top_urls for row in examples)
        bottom_count = sum(row["source_url"] in bottom_urls for row in examples)
        adequate = len(examples) >= minimum_pattern_samples and len(accounts) >= 2
        patterns.append({
            "hook_formula": formula_id,
            "hook_formula_name": examples[0]["hook_formula_name"],
            "sample_size": len(examples),
            "account_count": len(accounts),
            "median_outlier_multiple": round(float(median(multiples) or 0), 3),
            "top_third_count": top_count,
            "bottom_third_count": bottom_count,
            "adequate_sample": adequate,
            "sample_warning": "" if adequate else f"Need at least {minimum_pattern_samples} examples across 2 accounts.",
            "source_urls": [row["source_url"] for row in examples],
        })
    patterns.sort(key=lambda row: (-row["top_third_count"], -row["median_outlier_multiple"], row["hook_formula"]))
    if len(ranked) < 20:
        warnings.append({"code": "small_dataset", "detail": f"Only {len(ranked)} unique examples; treat patterns as directional."})
    account_count = len({row["account"] for row in ranked})
    if account_count < 4:
        warnings.append({"code": "few_accounts", "detail": f"Only {account_count} accounts are represented."})
    labels = sorted({row["dataset_label"] for row in ranked})
    if len(labels) != 1:
        warnings.append({"code": "mixed_dataset_labels", "labels": labels})
    recommendations = [
        {
            "hook_formula": pattern["hook_formula"],
            "evidence": {
                "sample_size": pattern["sample_size"],
                "account_count": pattern["account_count"],
                "median_outlier_multiple": pattern["median_outlier_multiple"],
                "top_third_count": pattern["top_third_count"],
                "bottom_third_count": pattern["bottom_third_count"],
            },
            "russian_hook_template": RUSSIAN_TEMPLATES.get(pattern["hook_formula"], RUSSIAN_TEMPLATES["unclassified"]),
            "status": "evidence_supported_template",
        }
        for pattern in patterns
        if pattern["adequate_sample"]
        and pattern["top_third_count"] > pattern["bottom_third_count"]
        and pattern["median_outlier_multiple"] >= 1.5
    ][:3]
    return {
        "schema": 1,
        "module": "ig-viral-adaptation",
        "analysis_mode": "manual_import_only",
        "dataset_labels": labels,
        "sample_size": len(ranked),
        "account_count": account_count,
        "baseline": "each account's manually supplied median views",
        "provenance_preserved": True,
        "ranked_examples": ranked,
        "patterns": patterns,
        "recommendations": recommendations,
        "warnings": warnings,
        "limitations": [
            "No Instagram scraping, login, private analytics access or engagement automation is implemented.",
            "Source URLs, account medians and hooks must be manually curated and verified by the owner.",
            "Templates are original Russian structures with placeholders; they are not permission to copy a competitor's script.",
        ],
    }
